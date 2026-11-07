"""How much of a GPU race slot does a race ever modify? (GPU layout, not the CPU's.)

Clones a race into N slots, drives them with a mix of abusive inputs (random chaos, holding into walls, reversing,
trick/item spam), and compares every slot with its pristine copy afterwards: the highest modified byte over all races
bounds the private heap a race really needs. It also checks that nothing was written into the shared template region.

    python tools/gpu_spike/extent_check.py --races 256 --r-kib 1024     # measure the extent
    python tools/gpu_spike/extent_check.py --races 256 --r-kib 640      # confirm a smaller slot is safe
"""

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import cupy as cp  # noqa: E402

import run_gpu  # noqa: E402
from brute_force import GO_FRAME, decode_rkg  # noqa: E402

STATE_WORDS = 26
DT = np.dtype([("b", "<i4"), ("sx", "<f4"), ("sy", "<f4"), ("t", "<i4")])


def scenarios(n, frames, rng):
    """Inputs [frame, race]: race i follows scenario i % 6."""
    inp = np.zeros((frames, n), DT)
    inp["b"] = 1
    kind = np.arange(n) % 6
    for i in range(n):
        k = kind[i]
        if k == 0:  # random chaos with sticky holds
            b = rng.choice([0, 1, 1, 1, 2, 3, 9, 11, 13, 15, 5], size=frames)
            sx = (rng.integers(0, 15, frames) - 7) / 7.0
            sy = (rng.integers(0, 15, frames) - 7) / 7.0
            t = np.where(rng.random(frames) < 0.03, rng.integers(1, 5, frames), 0)
            hold = rng.random(frames) < 0.85
            for f in range(1, frames):
                if hold[f]:
                    b[f], sx[f], sy[f] = b[f - 1], sx[f - 1], sy[f - 1]
            inp["b"][:, i], inp["sx"][:, i], inp["sy"][:, i], inp["t"][:, i] = b, sx, sy, t
        elif k == 1:  # hold left into walls
            inp["sx"][:, i] = -1.0
        elif k == 2:  # hold right into walls
            inp["sx"][:, i] = 1.0
        elif k == 3:  # reverse
            inp["b"][:, i] = 2
        elif k == 4:  # trick + item + drift spam
            inp["b"][:, i] = rng.choice([1, 5, 9, 13, 15], size=frames)
            inp["sx"][:, i] = rng.choice([-1.0, 0.0, 1.0], size=frames)
            inp["t"][:, i] = rng.integers(0, 5, frames)
        else:  # drift hard in circles
            inp["b"][:, i] = 11
            inp["sx"][:, i] = np.where((np.arange(frames) // 90) % 2 == 0, 1.0, -1.0)
    return inp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ghost", default=os.path.join(run_gpu.ROOT, "samples", "tracks", "luigi-circuit", "ghosts", "tas", "1142.rkg"))
    ap.add_argument("--races", type=int, default=256)
    ap.add_argument("--frames", type=int, default=3000, help="frames per race after the clone (0 = ghost length + 600)")
    ap.add_argument("--course", type=int)
    ap.add_argument("--character", type=int)
    ap.add_argument("--vehicle", type=int)
    ap.add_argument("--start-frame", type=int, default=GO_FRAME + 400,
                    help="frame the races are cloned at; 0 = from the start, like the search tools' slots")
    ap.add_argument("--r-kib", type=int, default=1024)
    ap.add_argument("--stack-kib", type=int, default=32)
    ap.add_argument("--block", type=int, default=32)
    ap.add_argument("--chunk", type=int, default=20)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()

    frames = decode_rkg(a.ghost)[3]
    combo = tuple(o if o is not None else c for o, c in zip((a.course, a.character, a.vehicle), run_gpu.combo_of(a.ghost)))
    g = run_gpu.GpuRace(a.stack_kib, *combo)
    g.init()
    if a.frames == 0:
        a.frames = len(frames) + 600
    if a.start_frame:
        g.run(frames[:a.start_frame])  # a race already under way
    space = g.space
    r = a.r_kib * 1024
    stride = r + run_gpu.STATICS_BYTES
    n = a.races
    used = 12 << 20
    shared_before = cp.asnumpy(space[r:used]).copy()

    slots = cp.zeros(stride * n, np.uint8)
    clone, layout = g.kernel("k_clone"), g.kernel("k_layout")
    step, state = g.kernel("k_step"), g.kernel("k_state")
    clone((n,), (256,), (space, space[run_gpu.MEMORY_SPACE_SIZE:], np.uint64(r), slots, np.uint64(stride), np.int32(n)))
    layout((1,), (1,), (slots, np.uint64(stride), np.uint64(r)))
    cp.cuda.Device().synchronize()
    pristine = slots.copy()

    rng = np.random.default_rng(a.seed)
    inp = scenarios(n, a.frames, rng)
    d_inp = cp.asarray(inp.reshape(-1).view(np.uint8))
    blocks = (n + a.block - 1) // a.block
    for f0 in range(0, a.frames, a.chunk):
        k = min(a.chunk, a.frames - f0)
        step((blocks,), (a.block,), (d_inp[f0 * 16 * n:], np.int32(k), np.int32(n), np.int32(1)))
        cp.cuda.Device().synchronize()
    out = cp.zeros((n, STATE_WORDS), np.uint32)
    state((blocks,), (a.block,), (out, np.int32(n)))
    res = cp.asnumpy(out)

    # Highest modified private-heap byte in each race (statics block excluded), in chunks to bound memory.
    worst, worst_by_kind = 0, {}
    cur = slots.reshape(n, stride)
    ref = pristine.reshape(n, stride)
    for s in range(0, n, 32):
        diff = (cur[s:s + 32, :r] != ref[s:s + 32, :r])
        idx = cp.where(diff.any(axis=1), (diff * cp.arange(r, dtype=cp.int32)[None, :]).max(axis=1), -1)
        for j, v in enumerate(cp.asnumpy(idx)):
            kind = (s + j) % 6
            worst = max(worst, int(v))
            worst_by_kind[kind] = max(worst_by_kind.get(kind, -1), int(v))
    shared_after = cp.asnumpy(space[r:used])
    names = ["chaos", "wall left", "wall right", "reverse", "spam", "drift circles"]
    print(f"R = {a.r_kib} KiB, {n} races x {a.frames} frames after frame {a.start_frame}")
    for k in range(6):
        print(f"  {names[k]:14s} highest modified byte: {worst_by_kind.get(k, -1) / 1024:8.1f} KiB")
    print(f"highest modified byte over all races: {worst} = {worst / 1024:.1f} KiB")
    print(f"shared template region unchanged: {bool((shared_before == shared_after).all())}")
    print(f"races still running normally (stage < 4): {int((res[:, 0] < 4).sum())}/{n}")


if __name__ == "__main__":
    main()
