"""Many races at once: clone one GPU race into N slots (pointer-relocating copy of the first R heap bytes + statics),
step all of them with the same ghost inputs, check every race still matches the CPU bit for bit, and time it.

    python tools/gpu_spike/bench_gpu.py --races 256 [--split 400] [--r-kib 1024]

Each slot is R bytes of private heap followed by the statics block; everything beyond R stays shared in the template
race (course data, parameters). A checksum of the template's shared region before/after shows whether any race wrote
into shared memory (which would mean R is too small).
"""

import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import cupy as cp  # noqa: E402

import run_gpu  # noqa: E402
from brute_force import decode_rkg  # noqa: E402

STATE_WORDS = 26


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ghost", default=os.path.join(run_gpu.ROOT, "samples", "tracks", "luigi-circuit", "ghosts", "tas", "1142.rkg"))
    ap.add_argument("--races", type=int, default=256)
    ap.add_argument("--split", type=int, default=400, help="frames the template runs before it is cloned")
    ap.add_argument("--r-kib", type=int, default=1024, help="private heap bytes per race")
    ap.add_argument("--block", type=int, default=32, help="threads per block in k_step")
    ap.add_argument("--chunk", type=int, default=20, help="frames per k_step launch (keep launches well under 2 s)")
    ap.add_argument("--stack-kib", type=int, default=32)
    ap.add_argument("--diverge", type=float, default=0.0,
                    help="per-race inputs: each frame, with this probability, a race picks a random stick/drift input "
                         "(throughput under realistic warp divergence; correctness is then not checked)")
    a = ap.parse_args()

    frames = decode_rkg(a.ghost)[3]
    ref, names, _ = run_gpu.cpu_reference(frames)
    want_cols = ["px", "py", "pz", "speed", "completion", "raceFrame"]
    want_idx = [names.index(c) for c in want_cols]

    g = run_gpu.GpuRace(a.stack_kib)
    g.init()
    g.run(frames[: a.split])  # template advanced to the split frame (also checks it against nothing; see run_gpu)
    space = g.space
    r = a.r_kib * 1024
    statics_bytes = run_gpu.STATICS_BYTES
    stride = r + statics_bytes
    n = a.races
    used = 12 << 20
    shared_before = int(cp.sum(space[r:used].astype(cp.uint64)))

    slots = cp.zeros(stride * n, np.uint8)
    print(f"{n} races x {stride / 2**20:.2f} MiB = {slots.nbytes / 2**30:.2f} GiB of slots")
    clone, layout = g.kernel("k_clone"), g.kernel("k_layout")
    step, state = g.kernel("k_step"), g.kernel("k_state")
    t = time.time()
    clone((n,), (256,), (space, space[run_gpu.MEMORY_SPACE_SIZE:], np.uint64(r), slots, np.uint64(stride), np.int32(n)))
    cp.cuda.Device().synchronize()
    print(f"clone: {time.time() - t:.3f}s")
    layout((1,), (1,), (slots, np.uint64(stride), np.uint64(r)))

    rest = frames[a.split:]
    inp = np.zeros(len(rest), dtype=[("b", "<i4"), ("sx", "<f4"), ("sy", "<f4"), ("t", "<i4")])
    for i, (b, tr, sx, sy) in enumerate(rest):
        inp[i] = (b, sx, sy, tr)
    per_race = 0
    if a.diverge > 0:
        rng = np.random.default_rng(7)
        many = np.repeat(inp[:, None], n, axis=1)  # [frame, race]
        hit = rng.random(many.shape) < a.diverge
        sticks = (rng.integers(0, 15, many.shape) - 7) / np.float32(7.0)
        many["sx"] = np.where(hit, sticks.astype(np.float32), many["sx"])
        many["b"] = np.where(hit & (rng.random(many.shape) < 0.5), many["b"] ^ 2, many["b"])  # toggle drift
        # inputs stay "sticky": a race keeps its deviation for the following frames
        for f in range(1, len(many)):
            keep = ~hit[f]
            many["sx"][f] = np.where(keep & hit[f - 1], many["sx"][f - 1], many["sx"][f])
        inp = many.reshape(-1)
        per_race = 1
    d_inp = cp.asarray(inp.view(np.uint8))
    blocks = (n + a.block - 1) // a.block
    out = cp.zeros((n, STATE_WORDS), np.uint32)
    t = time.time()
    worst = 0.0
    for f0 in range(0, len(rest), a.chunk):
        k = min(a.chunk, len(rest) - f0)
        t1 = time.time()
        off = f0 * 16 * (n if per_race else 1)
        step((blocks,), (a.block,), (d_inp[off:], np.int32(k), np.int32(n), np.int32(per_race)))
        cp.cuda.Device().synchronize()
        worst = max(worst, time.time() - t1)
    dt = time.time() - t
    state((blocks,), (a.block,), (out, np.int32(n)))
    res = cp.asnumpy(out)
    total = n * len(rest)
    print(f"stepped {n} races x {len(rest)} frames in {dt:.2f}s = {total / dt:,.0f} race-frames/s "
          f"(longest launch {worst:.3f}s)")

    if per_race:
        fin = res[:, 0] >= 4
        comp = res[:, 5 + 20].view(np.float32)
        print(f"divergent inputs: {int(fin.sum())}/{n} races finished; completion min/median/max "
              f"{comp.min():.3f}/{np.median(comp):.3f}/{comp.max():.3f}")
        return
    # every race must equal the CPU's final row (state layout: see runtime.cu k_state)
    cpu_last = ref[-1]
    exp = np.zeros(STATE_WORDS, np.uint32)
    exp[0], exp[1] = int(cpu_last[names.index("stage")]), int(cpu_last[names.index("raceFrame")])
    exp[2] = int(cpu_last[names.index("checkpoint")])
    cols_f = ["px", "py", "pz", "qx", "qy", "qz", "qw", "mqx", "mqy", "mqz", "mqw", "evx", "evy", "evz", "ivx", "ivy",
              "ivz", "speed", "speedRatio", "kclSpeedFactor", "completion"]
    exp_f = np.array([cpu_last[names.index(c)] for c in cols_f], np.float32).view(np.uint32)
    ok_f = (res[:, 5:] == exp_f).all(axis=1)
    ok_i = (res[:, 0] == exp[0]) & (res[:, 1] == exp[1]) & (res[:, 2] == exp[2])
    good = int((ok_f & ok_i).sum())
    print(f"races matching the CPU's final state bit for bit: {good}/{n}")
    if good < n:
        bad = int(np.nonzero(~(ok_f & ok_i))[0][0])
        print(f"  race {bad}: gpu {res[bad, :5]} {res[bad, 5:].view(np.float32)[:6]}")
        print(f"  cpu      {exp[:3]} {exp_f.view(np.float32)[:6]}")
    shared_after = int(cp.sum(space[r:used].astype(cp.uint64)))
    print(f"shared template region unchanged: {shared_before == shared_after}")


if __name__ == "__main__":
    main()
