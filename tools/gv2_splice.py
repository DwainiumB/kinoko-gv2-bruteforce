#!/usr/bin/env python3
"""Splice sweep: candidate's inputs up to row S-1, then the reference's inputs from row S+d (shifted by d) onward.

All (S, d) pairs run in one GPU batch. Each is scored on the L1-line crossing (sub-frame, from completion) and on the state
vs the reference at --at-rows (ahead in frames, lateral offset, EV, speed).

    python tools/gv2_splice.py --cand runs/gv2/gv2_L1hit_E.rkg --s 847 976 --d -3 1 --out runs/gv2/spliceE
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "gpu_spike"))
import cupy as cp  # noqa: E402

import brute_force as bf  # noqa: E402
from gpu_engine import Engine, make_inputs  # noqa: E402
from evolve import COL  # noqa: E402

G = "samples/tracks/ghost-valley-2/ghosts/"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--ref", default=G + "rGV2_27.818_slimpanda_best.rkg")
    ap.add_argument("--s", type=int, nargs=2, default=[847, 976])
    ap.add_argument("--d", type=int, nargs=2, default=[-3, 1])
    ap.add_argument("--to-row", type=int, default=1060)
    ap.add_argument("--at-rows", type=int, nargs="+", default=[976, 1000, 1050])
    ap.add_argument("--max-lat", type=float, default=1e9, help="rank splices off the ref line by more than this at the first --at-rows row last")
    ap.add_argument("--rank-comp", action="store_true", help="rank by race completion at the last --at-rows row (the ultra shortcut), then by the L1 line")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--out", default=None, help="write the best --top splices as <out>_<k>.rkg")
    a = ap.parse_args()

    c, ch, v, fc = bf.decode_rkg(a.cand)
    _, _, _, fr = bf.decode_rkg(a.ref)
    fc, fr = list(fc), list(fr)
    pairs = [(s, d) for s in range(a.s[0], a.s[1] + 1) for d in range(a.d[0], a.d[1] + 1)]
    n = len(pairs) + 1                       # slot 1 = the reference itself
    T = a.to_row

    def seq(s, d):
        out = list(fc[:s])
        for f in range(s, T + 1):
            g = f + d
            out.append(fr[g] if 0 <= g < len(fr) else (0, 0, 0.0, 0.0))
        return out

    seqs = [list(fr[:T + 1])] + [seq(s, d) for s, d in pairs]
    B = np.array([[x[0] for x in sq[:T + 1]] for sq in seqs], np.int32)
    TR = np.array([[x[1] for x in sq[:T + 1]] for sq in seqs], np.int32)
    SX = np.array([[x[2] for x in sq[:T + 1]] for sq in seqs], np.float32)
    SY = np.array([[x[3] for x in sq[:T + 1]] for sq in seqs], np.float32)

    eng = Engine(n + 1, course=c, character=ch, vehicle=v)
    eng.clone_template(1, n)
    Bc, TRc, SXc, SYc = (cp.asarray(x) for x in (B, TR, SX, SY))
    comp_prev = cp.zeros(n, cp.float32)
    cross = cp.full(n, cp.nan, cp.float32)
    snap = {}
    for f in range(T + 1):
        eng.step(1, n, make_inputs(Bc[:, f], TRc[:, f], SXc[:, f], SYc[:, f]))
        rows = eng.rows(1, n, f + 1)
        comp = rows[:, COL["completion"]].astype(cp.float32)
        hit = (comp >= 2.0) & (comp_prev < 2.0) & cp.isnan(cross) & (f > 900)
        cross = cp.where(hit, (f - 1) + (2.0 - comp_prev) / cp.maximum(comp - comp_prev, 1e-6), cross)
        comp_prev = comp
        if f in a.at_rows:
            snap[f] = cp.asnumpy(rows[:, [COL["px"], COL["pz"], COL["evx"], COL["evz"], COL["speed"], COL["completion"]]])
    cross = cp.asnumpy(cross)

    # reference path from slot 0 (the reference run) is needed for ahead/lat: rebuild it cheaply on the CPU dump instead
    import csv
    R = list(csv.DictReader(open(os.path.join(os.path.dirname(HERE), "runs/gv2/gv2_27818.csv"))))
    P = np.array([[float(r["px"]), float(r["pz"])] for r in R[:T + 60]])

    def ahead(x, z, r):
        lo, hi = max(0, r - 40), min(len(P) - 2, r + 40)
        seg = P[lo:hi + 1]
        k = int(np.argmin((seg[:, 0] - x) ** 2 + (seg[:, 1] - z) ** 2)) + lo
        k = min(k, len(P) - 2)
        dx, dz = P[k + 1] - P[k]
        s2 = max(dx * dx + dz * dz, 1e-6)
        t = ((x - P[k, 0]) * dx + (z - P[k, 1]) * dz) / s2
        lat = ((x - P[k, 0]) * dz - (z - P[k, 1]) * dx) / s2 ** 0.5
        return k + t - r, lat

    res = []
    for i in range(n):
        m = {"cross": cross[i]}
        for r in a.at_rows:
            x, z, evx, evz, sp, cm = snap[r][i]
            m[r] = ahead(x, z, r) + (float(np.hypot(evx, evz)), float(sp))
        res.append(m)
    ref_cross = res[0]["cross"]

    def line(m):
        s = f"L1 line {m['cross']:.2f} ({m['cross'] - ref_cross:+.2f}f)"
        for r in a.at_rows:
            ah, lat, ev, sp = m[r]
            s += f" | @{r} ahead {ah:+.2f}f lat {lat:+6.1f} ev {ev:4.1f} sp {sp:5.1f}"
        return s

    print(f"reference: {line(res[0])}")
    last = a.at_rows[-1]
    key = lambda i: (res[i]["cross"] if not np.isnan(res[i]["cross"]) else 1e9) + (0.0 if abs(res[i][a.at_rows[0]][1]) < a.max_lat else 1000.0)
    if a.rank_comp:
        key = lambda i: (-round(float(snap[last][i][5]), 3), res[i]["cross"] if not np.isnan(res[i]["cross"]) else 1e9)
    order = sorted(range(1, n), key=key)
    for rank, i in enumerate(order[:a.top]):
        s, d = pairs[i - 1]
        print(f"S={s} d={d:+d}: {line(res[i])} | comp@{last} {snap[last][i][5]:.4f} (ref {snap[last][0][5]:.4f})")
        if a.out:
            path = f"{a.out}_{rank}.rkg"
            open(path, "wb").write(bf.encode_rkg(c, ch, v, seqs[i], 0))
    print("best L1 line among all:", min((res[i]["cross"], pairs[i - 1]) for i in range(1, n) if not np.isnan(res[i]["cross"])))


if __name__ == "__main__":
    main()
