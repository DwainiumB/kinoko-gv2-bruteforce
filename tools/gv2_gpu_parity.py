#!/usr/bin/env python3
"""GPU vs CPU parity for a ghost: step the GPU engine with the ghost's inputs and compare every row to a CPU replay dump."""
import csv, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "gpu_spike"))
import cupy as cp
import brute_force as bf
from gpu_engine import Engine, make_inputs
from evolve import COLS, COL

rkg, dump = sys.argv[1], sys.argv[2]
upto = int(sys.argv[3]) if len(sys.argv) > 3 else None
c, ch, v, fr = bf.decode_rkg(rkg)
cpu = list(csv.reader(open(dump)))[1:]
n = min(len(fr), len(cpu), upto or 10**9)
e = Engine(2, course=c, character=ch, vehicle=v)
e.clone_template(0, 1)
names = COLS[1:]
bad = 0
for f in range(n):
    b, t, sx, sy = fr[f]
    e.step(0, 1, make_inputs(cp.asarray([b], cp.int32), cp.asarray([t], cp.int32), cp.asarray([sx], cp.float32), cp.asarray([sy], cp.float32)))
    r = cp.asnumpy(e.rows(0, 1, f + 1))[0]
    row = cpu[f]
    for nm in ("px", "py", "pz", "qx", "qy", "qz", "qw", "evx", "evy", "evz", "speed", "completion", "flags"):
        gi = COL[nm]; ci = COLS.index(nm)
        gv, cv = float(r[gi]), float(row[ci])
        if gv != cv and not (abs(gv - cv) <= 1e-6 * max(1.0, abs(cv))):
            if bad < 10:
                print(f"MISMATCH frame {f} {nm}: gpu {gv!r} cpu {cv!r}")
            bad += 1
print(f"course {c} char {ch} veh {v}: compared {n} frames, mismatching values {bad}")
