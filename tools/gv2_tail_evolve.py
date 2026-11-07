#!/usr/bin/env python3
"""GV2 L1: fit the superhops after the fast block hit (rows --from-row .. --to-row), on the GPU.

Genome per row: stick X, stick Y (-7..7), face buttons, trick. Rows before --from-row = the base run (the hit, e.g.
gv2_L1hit_E). Rows after --to-row = the reference's inputs at row + --tail-shift (the 27.818's L2 approach).
Mutations: stick point edits, hop-timing shifts (a button run boundary moves one frame), single-frame button toggles
(11 <-> 1), trick copies from the reference (+-1 frame), and block copies from another good genome.

Cost (lower = better):
    w_cross * (sub-frame L1-line crossing - reference crossing)           (frames; not crossed by --to-row + 10: 1000)
  + w_lat   * mean over --lat-rows of max(lateral offset from the ref path - lat_tol, 0)   (the lap-2 line)
  - w_ev    * min(EV at --ev-row, ev_cap)
  + w_sp    * |speed - ref speed| at --ev-row
  + w_each  * changed values vs the base

    python tools/gv2_tail_evolve.py --base runs/gv2/gv2_L1hit_E.rkg --seed runs/gv2/spliceE_0.rkg --out runs/gv2/tailA
"""
import argparse
import csv
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "gpu_spike"))
import cupy as cp  # noqa: E402

import brute_force as bf  # noqa: E402
from gpu_engine import Engine, make_inputs  # noqa: E402
from evolve import COL  # noqa: E402

ROOT = os.path.dirname(HERE)
G = os.path.join(ROOT, "samples/tracks/ghost-valley-2/ghosts/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.path.join(ROOT, "runs/gv2/gv2_L1hit_E.rkg"))
    ap.add_argument("--ref", default=G + "rGV2_27.818_slimpanda_best.rkg")
    ap.add_argument("--ref-dump", default=os.path.join(ROOT, "runs/gv2/gv2_27818.csv"))
    ap.add_argument("--seed", action="append", default=[])
    ap.add_argument("--from-row", type=int, default=849)
    ap.add_argument("--to-row", type=int, default=990)
    ap.add_argument("--tail-shift", type=int, default=0)
    ap.add_argument("--sim-to", type=int, default=1000)
    ap.add_argument("--lat-rows", type=int, nargs="+", default=[976, 990])
    ap.add_argument("--ev-row", type=int, default=976)
    ap.add_argument("--ev2-rows", type=int, nargs="*", default=[], help="rows where EV is rewarded too (the 2nd block bounce, ~1032/1044)")
    ap.add_argument("--w-ev2", type=float, default=2.0)
    ap.add_argument("--ev2-cap", type=float, default=50.0)
    ap.add_argument("--ahead-row", type=int, default=None, help="reward along-track progress on the ref path at this row (w-ahead per frame)")
    ap.add_argument("--w-ahead", type=float, default=100.0)
    ap.add_argument("--sync-rows", type=int, nargs="*", default=[], help="rows where the distance to the reference position at row + tail_shift costs --w-sync per unit (mean)")
    ap.add_argument("--w-sync", type=float, default=1.0)
    ap.add_argument("--sync-cap", type=float, default=3000.0)
    ap.add_argument("--sync-y-from", type=int, default=None, help="from this row on, the sync distance includes height (py): did the kart take the same jump")
    ap.add_argument("--comp-row", type=int, default=None, help="cost w-comp per unit of race completion short of the reference's (at row + tail_shift) at this row: did the ultra shortcut happen")
    ap.add_argument("--w-comp", type=float, default=2000.0)
    ap.add_argument("--pop", type=int, default=2048)
    ap.add_argument("--gens", type=int, default=300)
    ap.add_argument("--elite", type=float, default=0.08)
    ap.add_argument("--w-cross", type=float, default=100.0)
    ap.add_argument("--line-comp", type=float, default=2.0, help="completion value of the line scored by w-cross (2.0 = L1 line, 4.0 = finish)")
    ap.add_argument("--cross-after", type=int, default=900, help="only count line crossings after this row")
    ap.add_argument("--w-lat", type=float, default=0.5)
    ap.add_argument("--lat-tol", type=float, default=40.0)
    ap.add_argument("--w-ev", type=float, default=2.0)
    ap.add_argument("--ev-cap", type=float, default=45.0)
    ap.add_argument("--w-sp", type=float, default=1.0)
    ap.add_argument("--w-each", type=float, default=0.3)
    ap.add_argument("--p-btn", type=float, default=0.35, help="share of mutations that move hop timing / toggle a button")
    ap.add_argument("--p-trick", type=float, default=0.05)
    ap.add_argument("--seed-rng", type=int, default=1)
    ap.add_argument("--time-limit", type=float, default=1500.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed_rng)

    c, ch, v, fb = bf.decode_rkg(a.base)
    fr = list(bf.decode_rkg(a.ref)[3])
    fb = list(fb)
    R0, R1, T = a.from_row, a.to_row, a.sim_to
    W = R1 - R0 + 1
    n = a.pop

    def full(frames):
        """frames up to R1 from `frames`, then the reference (shifted) up to T."""
        out = list(frames[:R1 + 1]) + [fr[f + a.tail_shift] for f in range(R1 + 1, T + 1)]
        while len(out) < T + 1:
            out.append((0, 0, 0.0, 0.0))
        return out

    fb = full(fb + [(0, 0, 0.0, 0.0)] * max(0, R1 + 1 - len(fb)))

    def genome(frames):
        return np.array([[round(frames[f][2] * 7), round(frames[f][3] * 7), frames[f][0], frames[f][1]] for f in range(R0, R1 + 1)], np.int8)

    base_g = genome(fb)
    ref_g = genome(fr)
    seeds = [base_g] + [genome(list(bf.decode_rkg(p)[3])) for p in a.seed]

    # reference: path, crossing, speed
    R = list(csv.DictReader(open(a.ref_dump)))
    P = cp.asarray(np.array([[float(r["px"]), float(r["pz"])] for r in R[:T + 60]], np.float32))
    PY = cp.asarray(np.array([float(r["py"]) for r in R[:T + 60]], np.float32))
    comp = [float(r["completion"]) for r in R]
    i = next(k for k in range(a.cross_after, len(comp)) if comp[k] >= a.line_comp)
    ref_cross = (i - 1) + (a.line_comp - comp[i - 1]) / (comp[i] - comp[i - 1])
    ref_sp = float(R[a.ev_row]["speed"])

    def ahead_lat(rows, f):
        lo, hi = max(0, f - 25), f + 25
        px, pz = rows[:, COL["px"]], rows[:, COL["pz"]]
        seg = P[lo:hi]
        k = cp.minimum((((px[:, None] - seg[None, :, 0]) ** 2 + (pz[:, None] - seg[None, :, 1]) ** 2)).argmin(axis=1), hi - lo - 2)
        x0, z0, x1, z1 = seg[k, 0], seg[k, 1], P[lo + k + 1, 0], P[lo + k + 1, 1]
        dx, dz = x1 - x0, z1 - z0
        s2 = cp.maximum(dx * dx + dz * dz, 1e-6)
        return (lo + k).astype(cp.float32) + ((px - x0) * dx + (pz - z0) * dz) / s2 - f

    def lat_of(rows, f):
        lo, hi = max(0, f - 25), f + 25
        px, pz = rows[:, COL["px"]], rows[:, COL["pz"]]
        seg = P[lo:hi]
        k = cp.minimum((((px[:, None] - seg[None, :, 0]) ** 2 + (pz[:, None] - seg[None, :, 1]) ** 2)).argmin(axis=1), hi - lo - 2)
        x0, z0, x1, z1 = seg[k, 0], seg[k, 1], P[lo + k + 1, 0], P[lo + k + 1, 1]
        dx, dz = x1 - x0, z1 - z0
        return cp.abs((px - x0) * dz - (pz - z0) * dx) / cp.sqrt(cp.maximum(dx * dx + dz * dz, 1e-6))

    eng = Engine(n + 2, course=c, character=ch, vehicle=v)
    eng.clone_template(0, 1)
    for f in range(R0):
        b, t, sx, sy = fb[f]
        eng.step(0, 1, make_inputs(cp.asarray([b], cp.int32), cp.asarray([t], cp.int32), cp.asarray([sx], cp.float32), cp.asarray([sy], cp.float32)))
    tail = fb[R1 + 1:T + 1]

    def mutate(g):
        for _ in range(int(rng.integers(1, 4))):
            k = int(rng.integers(0, W))
            r_ = rng.random()
            if r_ < a.p_btn:
                if rng.random() < 0.6:          # move a hop-timing boundary by one frame
                    edges = np.nonzero(g[1:, 2] != g[:-1, 2])[0] + 1
                    if len(edges):
                        e = int(rng.choice(edges))
                        if rng.random() < 0.5:
                            g[e, 2] = g[e - 1, 2]
                        else:
                            g[e - 1, 2] = g[e, 2]
                else:                           # toggle a single frame between 11 and 1
                    g[k, 2] = 1 if g[k, 2] == 11 else 11
            elif r_ < a.p_btn + a.p_trick:
                kk = int(np.clip(k + rng.integers(-1, 2), 0, W - 1))
                g[k, 3] = ref_g[kk, 3] if rng.random() < 0.7 else 0
            else:
                ax = int(rng.integers(0, 2))
                q = rng.random()
                if q < 0.5:
                    g[k, ax] = np.clip(g[k, ax] + rng.choice([-2, -1, 1, 2]), -7, 7)
                elif q < 0.8:
                    g[k, ax] = rng.choice([-7, 0, 7]) if rng.random() < 0.6 else rng.integers(-7, 8)
                else:
                    g[k, ax] = base_g[k, ax]
        return g

    pop = np.zeros((n, W, 4), np.int8)
    for i in range(n):
        s = seeds[i % len(seeds)].copy()
        if i >= len(seeds):
            s = mutate(s)
        pop[i] = s

    def evaluate(pop):
        eng.copy([0] * n, list(range(1, n + 1)))
        G_ = cp.asarray(pop.astype(np.float32))
        cprev = cp.zeros(n, cp.float32)
        cross = cp.full(n, cp.nan, cp.float32)
        lat = cp.zeros(n, cp.float32)
        ev = cp.zeros(n, cp.float32)
        sp = cp.zeros(n, cp.float32)
        clast = cp.zeros(n, cp.float32)
        ev2 = cp.zeros(n, cp.float32)
        ahd = cp.zeros(n, cp.float32)
        sync = cp.zeros(n, cp.float32)
        cshort = cp.zeros(n, cp.float32)
        for f in range(R0, T + 1):
            if f <= R1:
                k = f - R0
                inp = make_inputs(G_[:, k, 2].astype(cp.int32), G_[:, k, 3].astype(cp.int32), G_[:, k, 0] / 7.0, G_[:, k, 1] / 7.0)
            else:
                b, t, sx, sy = tail[f - R1 - 1]
                inp = make_inputs(cp.full(n, b, cp.int32), cp.full(n, t, cp.int32), cp.full(n, sx, cp.float32), cp.full(n, sy, cp.float32))
            eng.step(1, n, inp)
            rows = eng.rows(1, n, f + 1)
            cm = rows[:, COL["completion"]].astype(cp.float32)
            hit = (cm >= a.line_comp) & (cprev < a.line_comp) & cp.isnan(cross) & (f > a.cross_after)
            cross = cp.where(hit, (f - 1) + (a.line_comp - cprev) / cp.maximum(cm - cprev, 1e-6), cross)
            cprev = cm
            clast = cm
            if f in a.lat_rows:
                lat += cp.maximum(lat_of(rows, f) - a.lat_tol, 0.0) / len(a.lat_rows)
            if a.comp_row is not None and f == a.comp_row:
                cshort = cp.maximum(comp[f + a.tail_shift] - cm, 0.0).astype(cp.float32)
            if f in a.sync_rows:
                g_ = f + a.tail_shift
                d2_ = (rows[:, COL["px"]] - P[g_, 0]) ** 2 + (rows[:, COL["pz"]] - P[g_, 1]) ** 2
                if a.sync_y_from is not None and f >= a.sync_y_from:
                    d2_ = d2_ + (rows[:, COL["py"]] - PY[g_]) ** 2
                d_ = cp.sqrt(d2_)
                sync += cp.minimum(d_, a.sync_cap).astype(cp.float32) / len(a.sync_rows)
            if f in a.ev2_rows:
                ev2 += cp.minimum(cp.hypot(rows[:, COL["evx"]], rows[:, COL["evz"]]), a.ev2_cap).astype(cp.float32) / len(a.ev2_rows)
            if a.ahead_row is not None and f == a.ahead_row:
                ahd = cp.clip(ahead_lat(rows, f), -60.0, 5.0).astype(cp.float32)
                ahd = cp.where(lat_of(rows, f) > 300.0, -60.0, ahd).astype(cp.float32)
            if f == a.ev_row:
                ev = cp.hypot(rows[:, COL["evx"]], rows[:, COL["evz"]]).astype(cp.float32)
                sp = rows[:, COL["speed"]].astype(cp.float32)
        dcross = cp.where(cp.isnan(cross), 1000.0 + 1000.0 * cp.maximum(a.line_comp - clast, 0), cross - ref_cross)
        edits = cp.asarray((pop != base_g[None]).sum(axis=(1, 2)).astype(np.float32))
        cost = (a.w_cross * dcross + a.w_lat * lat - a.w_ev * cp.minimum(ev, a.ev_cap) + a.w_sp * cp.abs(sp - ref_sp) + a.w_each * edits
                - a.w_ev2 * ev2 - a.w_ahead * ahd + a.w_sync * sync + a.w_comp * cshort)
        return {k: cp.asnumpy(x) for k, x in dict(cost=cost, dcross=dcross, lat=lat, ev=ev, sp=sp, edits=edits, ev2=ev2, ahd=ahd, sync=sync, cshort=cshort).items()}

    def line(m, i):
        return (f"cost {m['cost'][i]:8.1f} | L1 line {m['dcross'][i]:+.3f}f vs 27.818 | off-line excess {m['lat'][i]:6.1f} | "
                f"sync {m['sync'][i]:6.1f} | comp short {m['cshort'][i]:.3f} | EV2 {m['ev2'][i]:4.1f} | ahead@{a.ahead_row} {m['ahd'][i]:+.2f}f | EV@{a.ev_row} {m['ev'][i]:4.1f} sp {m['sp'][i]:5.1f} (ref {ref_sp:.1f}) | edits {int(m['edits'][i])}")

    t0 = time.time()
    m = evaluate(pop)
    print(f"reference L1 crossing {ref_cross:.3f}", flush=True)
    print(f"base : {line(m, 0)}", flush=True)
    for j in range(1, len(seeds)):
        print(f"seed{j}: {line(m, j)}", flush=True)
    for g in range(1, a.gens + 1):
        order = np.argsort(m["cost"])
        ne = max(2, int(a.elite * n))
        new = np.empty_like(pop)
        new[:ne] = pop[order[:ne]]
        third = max(ne + 1, n // 3)
        for i in range(ne, n):
            ch_ = pop[order[rng.integers(0, third, 2)].min()].copy()
            if rng.random() < 0.3:
                p2 = pop[order[rng.integers(0, third, 2)].min()]
                c1, c2 = sorted(rng.integers(0, W, 2))
                ch_[c1:c2 + 1] = p2[c1:c2 + 1]
            new[i] = mutate(ch_)
        pop = new
        m = evaluate(pop)
        if g % 5 == 0 or g == a.gens:
            i = int(np.argmin(m["cost"]))
            print(f"gen {g:3d}: {line(m, i)} [{time.time() - t0:.0f}s]", flush=True)
        if time.time() - t0 > a.time_limit:
            print(f"time limit reached at gen {g}", flush=True)
            break

    order = np.argsort(m["cost"])
    seen, wrote = set(), 0
    for i in order:
        key = pop[i].tobytes()
        if key in seen:
            continue
        seen.add(key)
        out = list(fb)
        for k in range(W):
            sx, sy, b, t = (int(x) for x in pop[i][k])
            out[R0 + k] = (b, t, sx / 7.0, sy / 7.0)
        # keep the reference's frames after sim_to so the file carries the L2/L3 inputs too
        out = out + [fr[f + a.tail_shift] for f in range(T + 1, len(fr) - max(a.tail_shift, 0))]
        path = f"{a.out}_{wrote}.rkg"
        open(path, "wb").write(bf.encode_rkg(c, ch, v, out, 0))
        print(f"candidate {wrote}: {line(m, i)} -> {path}", flush=True)
        wrote += 1
        if wrote >= 6:
            break
    print("done", flush=True)


if __name__ == "__main__":
    main()
