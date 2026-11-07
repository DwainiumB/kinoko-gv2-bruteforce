"""Run one Kinoko race on the GPU and compare it frame by frame, bit for bit, with the CPU build.

    python tools/gpu_spike/build_gpu.py
    python tools/gpu_spike/run_gpu.py --ghost samples/tracks/luigi-circuit/ghosts/tas/1142.rkg [--frames 600]

The GPU race is initialised on the device by the real engine code (runtime.cu k_init) from the game files uploaded by
this script, then driven with the ghost's inputs. The CPU reference is `kinoko_host search` (see kinoko_search.find_host_binary).
"""

import argparse
import os
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))

import cupy as cp  # noqa: E402

from brute_force import _yaz_decompress, decode_rkg  # noqa: E402
from kinoko_search import KinokoSearch, find_host_binary  # noqa: E402

CUBIN = os.path.join(HERE, "out", "kinoko.cubin")
CPU_BINARY = find_host_binary()
MEMORY_SPACE_SIZE = 0x4000000
STATICS_BYTES = 64 * 128
STATE_WORDS = 26
INT_COLS = ["stage", "raceFrame", "checkpoint", "driftState", "mtCharge"]
FLOAT_COLS = ["px", "py", "pz", "qx", "qy", "qz", "qw", "mqx", "mqy", "mqz", "mqw", "evx", "evy", "evz", "ivx", "ivy",
              "ivz", "speed", "speedRatio", "kclSpeedFactor", "completion"]


def _course_names():
    """include/Common.hh COURSE_NAMES, by course id (None for unused ids): the archive the engine opens for a course."""
    import re
    text = open(os.path.join(ROOT, "include", "Common.hh"), encoding="utf-8").read()
    body = text[text.index("COURSE_NAMES["):]
    body = body[body.index("{") + 1:body.index("};")]
    return [None if t == "nullptr" else t.strip('"') for t in re.findall(r'"[^"]*"|nullptr', body)]


COURSE_NAMES = _course_names()


def course_files(course):
    """The only two files a race opens (ResourceManager): Common.szs, which holds every character's and vehicle's data,
    and the course archive."""
    if not (0 <= course < len(COURSE_NAMES)) or not COURSE_NAMES[course]:
        raise ValueError(f"no course archive for course id {course}")
    return ["Race/Common.szs", f"Race/Course/{COURSE_NAMES[course]}.szs"]


def combo_of(rkg):
    """(course, character, vehicle) from a ghost's header."""
    c, ch, v, _frames = decode_rkg(rkg)
    return c, ch, v


def expanded(path):
    """Host-side Yaz0 decompression, cached next to the cubin."""
    cache = os.path.join(HERE, "out", os.path.basename(path) + ".expanded")
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(path):
        return open(cache, "rb").read()
    data = _yaz_decompress(open(path, "rb").read())
    with open(cache, "wb") as fh:
        fh.write(data)
    return data


class GpuRace:
    def __init__(self, stack_kib, course=8, character=22, vehicle=32, auto=False):
        self.combo = (course, character, vehicle)
        self.auto = bool(auto)
        cp.cuda.runtime.deviceSetLimit(0, stack_kib * 1024)  # cudaLimitStackSize, per thread
        self.mod = cp.RawModule(path=CUBIN)
        self.keep = []  # device buffers that must outlive the race
        table = b""
        files = course_files(course)
        for rel in files:
            raw = open(os.path.join(ROOT, rel), "rb").read()
            exp = expanded(os.path.join(ROOT, rel))
            bufs = [cp.asarray(np.frombuffer(rel.encode() + b"\0", np.uint8)), cp.asarray(np.frombuffer(raw, np.uint8)),
                    cp.asarray(np.frombuffer(exp, np.uint8))]
            self.keep += bufs
            table += struct.pack("<QQQQQ", bufs[0].data.ptr, bufs[1].data.ptr, len(raw), bufs[2].data.ptr, len(exp))
        self.mod.get_global("g_kinokoFiles").copy_from_host(np.frombuffer(table, np.uint8).ctypes.data, len(table))
        count = np.array([len(files)], np.int32)
        self.mod.get_global("g_kinokoFileCount").copy_from_host(count.ctypes.data, 4)
        self.space = cp.zeros(MEMORY_SPACE_SIZE + STATICS_BYTES, np.uint8)
        self.state = None

    def kernel(self, name):
        return self.mod.get_function(name)

    def init(self, course=None, character=None, vehicle=None):
        """Builds the template race for this GpuRace's (course, character, vehicle); the arguments must match it."""
        if (course, character, vehicle) != (None, None, None) and (course, character, vehicle) != self.combo:
            raise ValueError(f"init{(course, character, vehicle)} doesn't match the files loaded for {self.combo}")
        course, character, vehicle = self.combo
        flag = np.array([1 if self.auto else 0], np.int32)
        self.mod.get_global("g_driftAuto").copy_from_host(flag.ctypes.data, 4)
        t = time.time()
        self.kernel("k_init")((1,), (1,), (self.space, np.uint64(MEMORY_SPACE_SIZE), np.int32(course),
                                         np.int32(character), np.int32(vehicle)))
        cp.cuda.Device().synchronize()
        return time.time() - t

    def run(self, frames):
        """Step through `frames` [(buttons, trick, sx, sy)], recording the state after every frame."""
        inp = np.zeros(len(frames), dtype=[("b", "<i4"), ("sx", "<f4"), ("sy", "<f4"), ("t", "<i4")])
        for i, (b, t, sx, sy) in enumerate(frames):
            inp[i] = (b, sx, sy, t)
        d_inp = cp.asarray(inp.view(np.uint8))
        out = cp.zeros((len(frames), 128), np.float64)
        step, row = self.kernel("k_step"), self.kernel("k_rows")
        t = time.time()
        for i in range(len(frames)):
            step((1,), (1,), (d_inp[i * 16:], np.int32(1), np.int32(1), np.int32(0)))
            row((1,), (1,), (out[i], np.uint32(i), np.int32(1)))
            if i % 200 == 199:
                cp.cuda.Device().synchronize()  # keep the queue short so a hang shows up quickly
        cp.cuda.Device().synchronize()
        return cp.asnumpy(out), time.time() - t


def cpu_reference(frames, combo=(8, 22, 32)):
    """The CPU state rows (host/FrameState.cc, 109 columns) after every frame, and the column names."""
    race = KinokoSearch(binary=CPU_BINARY, course=combo[0], character=combo[1], vehicle=combo[2])
    t = time.time()
    rows = np.array([race.step(b, sx, sy, tr) for b, tr, sx, sy in frames])
    return rows, race.cols, time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ghost", default=os.path.join(ROOT, "samples", "tracks", "luigi-circuit", "ghosts", "tas", "1142.rkg"))
    ap.add_argument("--frames", type=int, default=0, help="0 = the whole ghost")
    ap.add_argument("--stack-kib", type=int, default=32)
    ap.add_argument("--course", type=int, help="override the ghost's course (its inputs then just drive the kart)")
    ap.add_argument("--character", type=int, help="override the ghost's character")
    ap.add_argument("--vehicle", type=int, help="override the ghost's vehicle")
    a = ap.parse_args()
    frames = decode_rkg(a.ghost)[3]
    combo = combo_of(a.ghost)
    combo = tuple(o if o is not None else c for o, c in zip((a.course, a.character, a.vehicle), combo))
    if a.frames:
        frames = frames[: a.frames]
    print(f"{len(frames)} frames from {os.path.basename(a.ghost)}")

    print(f"course {combo[0]} ({COURSE_NAMES[combo[0]]}), character {combo[1]}, vehicle {combo[2]}")
    ref, names, cpu_t = cpu_reference(frames, combo)
    print(f"CPU reference: {cpu_t:.2f}s (incl. pipe overhead)")

    g = GpuRace(a.stack_kib, *combo)
    print(f"GPU init: {g.init():.2f}s")
    got, gpu_t = g.run(frames)
    print(f"GPU: {len(frames)} frames in {gpu_t:.2f}s ({gpu_t / len(frames) * 1e6:.0f} us/frame, one race, 2 launches/frame)")

    n = len(names)
    assert (got[:, 0] == n).all(), f"GPU rows have {set(got[:, 0])} values, CPU rows {n}"
    got = got[:, 1:]
    # every column is a float32 or a small integer: compare as float32 bits (the CPU text has 9 significant digits)
    g32, c32 = got[:, :n].astype(np.float32), ref.astype(np.float32)
    bad = np.nonzero((g32.view(np.uint32) != c32.view(np.uint32)).any(axis=1))[0]
    if len(bad) == 0:
        print(f"ALL {len(frames)} FRAMES BIT-IDENTICAL on all {n} state columns")
        return 0
    f = bad[0]
    print(f"first mismatch at frame {f} ({len(bad)} frames differ)")
    for k, name in enumerate(names):
        if g32[f, k].view(np.uint32) != c32[f, k].view(np.uint32):
            print(f"   {name:15s} gpu={g32[f, k]!r:>22}  cpu={c32[f, k]!r:>22}   (frame {f - 1}: {c32[f - 1, k]!r})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
