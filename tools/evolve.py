#!/usr/bin/env python3
"""(Yoshi Falls tool, kept as the original the gv2_* searches were built from; not used by them.)

Population search over the whole stick sequence of the ride (default web 464 .. 662).

A genome is one stick value (-7..+7) per row; buttons (hop, drift held, the mushroom press) come from the base run and are fixed.
Every individual is played on the GPU from the state at the landing to the SMT release and scored by a penalty:

    charge   : the MT + SMT counters at --need-row must reach --need-chs (570 = SMT charged)          (dominant)
    legality : wall-collision flags, respawn, the drift ending, the drift direction, grounded rows,
               frames without a grounded wheel in --zero-rows beyond --zero-cap, keeping up with the
               reference's race completion, distance to its path
    airtime  : airborne frames from --air-from (small weight)

(mu + lambda) evolution: tournament selection, one-/two-point crossover, point mutations, and block shifts (delete one frame and
duplicate another, which moves a whole stretch of the sequence one frame earlier or later -- the move a per-frame beam cannot make).

    python tools/evolve.py --base ..._air15_hold.rkg --seed a.rkg --seed b.rkg --ref ...WIP.rkg --out ...evo
"""
import argparse
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

from gpu_engine import ROW_COLUMN as COL, ROW_COLUMN_NAMES as COLS  # noqa: E402,F401
SMT = 117


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--seed", action="append", default=[], help="runs whose sticks seed the population (same car/driver)")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--from-row", type=int, default=463, help="state is taken after this row; sticks are evolved from the next row")
    ap.add_argument("--to-row", type=int, default=660)
    ap.add_argument("--need-row", type=int, default=658)
    ap.add_argument("--need-chs", type=float, default=570.0)
    ap.add_argument("--pop", type=int, default=3000)
    ap.add_argument("--gens", type=int, default=300)
    ap.add_argument("--elite", type=float, default=0.1)
    ap.add_argument("--air-from", type=int, default=562)
    ap.add_argument("--zero-rows", type=int, nargs=2, default=[620, 660])
    ap.add_argument("--zero-cap", type=int, default=3)
    ap.add_argument("--zero2-rows", type=int, nargs=2, default=None, help="second window of rows with no airborne frame allowed beyond --zero2-cap")
    ap.add_argument("--zero2-cap", type=int, default=0)
    ap.add_argument("--counter-rows", type=int, nargs=2, default=None, help="rows where the drift direction must be the OPPOSITE one (hopStickX == +1): the counter drift after the SMT release")
    ap.add_argument("--second-from", type=int, default=None, help="rows from this one on: the first row where mt+smt charge reaches --need-chs (the SECOND SMT) is scored: --w-second per row of delay")
    ap.add_argument("--w-second", type=float, default=30.0)
    ap.add_argument("--w-final", type=float, default=0.0, help="cost per unit of race completion lost against the reference at the last row (negative = reward for being ahead)")
    ap.add_argument("--w-counter", type=float, default=400.0, help="cost per row without the opposite-direction (counter) drift inside --counter-rows")
    ap.add_argument("--drift-until", type=int, default=99999, help="the drift-state / drift-direction penalties apply only to rows up to this one (allows a re-hop / counter drift after the release)")
    ap.add_argument("--ground-rows", type=int, nargs=2, default=[490, 505])
    ap.add_argument("--keepup", type=float, default=0.0012)
    ap.add_argument("--max-gap", type=float, default=250.0)
    ap.add_argument("--hang-rows", type=int, nargs=2, default=None, metavar=("A", "B"),
                    help="the hang-off pose: at most --hang-max wheels with floor contact on every row of this range")
    ap.add_argument("--hang-max", type=int, default=1)
    ap.add_argument("--stay-rows", type=int, nargs=2, default=None, metavar=("A", "B"),
                    help="after the SMT release: keep on the road -- height within --stay-dy of the reference path, and at most "
                         "--stay-nowheel frames without any wheel on a floor, on every row of this range")
    ap.add_argument("--stay-dy", type=float, default=120.0)
    ap.add_argument("--stay-nowheel", type=int, default=8)
    ap.add_argument("--w-charge", type=float, default=40.0)
    ap.add_argument("--w-air", type=float, default=3.0)
    ap.add_argument("--freeze-until", type=int, default=0, help="rows before this keep the seed's sticks (e.g. the run-up/line you trust)")
    ap.add_argument("--freeze-from", type=int, default=0,
                    help="rows from this one on keep the BASE run's sticks (only the sticks before it evolve)")
    ap.add_argument("--seed-rng", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed_rng)

    c, ch, v, fr = bf.decode_rkg(a.base)
    fr = list(fr)
    R0, R1 = a.from_row + 1, a.to_row
    L = R1 - R0 + 1
    n = a.pop
    eng = Engine(n + 2, course=c, character=ch, vehicle=v)

    # reference
    cref = bf.decode_rkg(a.ref)
    rf = list(cref[3])
    ref = {k: np.zeros(R1 + 3, np.float32) for k in ("px", "py", "pz", "comp", "chs")}
    er = Engine(2, course=cref[0], character=cref[1], vehicle=cref[2])
    er.clone_template(0, 1)
    for f in range(R1 + 3):
        b, t, sx, sy = rf[f]
        er.step(0, 1, make_inputs(cp.asarray([b], cp.int32), cp.asarray([t], cp.int32), cp.asarray([sx], cp.float32), cp.asarray([sy], cp.float32)))
        r = cp.asnumpy(er.rows(0, 1, f + 1))[0]
        ref["px"][f], ref["pz"][f], ref["comp"][f] = r[COL["px"]], r[COL["pz"]], r[COL["completion"]]
        ref["py"][f] = r[COL["py"]]
        ref["chs"][f] = min(float(r[COL["mtCharge"]]), 270.0) + float(r[SMT])
    del er
    Rp = {k: cp.asarray(x) for k, x in ref.items()}

    # state at the start row
    eng.clone_template(0, 1)
    for f in range(R0):
        b, t, sx, sy = fr[f]
        eng.step(0, 1, make_inputs(cp.asarray([b], cp.int32), cp.asarray([t], cp.int32), cp.asarray([sx], cp.float32), cp.asarray([sy], cp.float32)))
    base_btn = np.array([fr[f][0] for f in range(R0, R1 + 1)], np.int32)
    base_trk = np.array([fr[f][1] for f in range(R0, R1 + 1)], np.int32)

    def sticks_of(path):
        cc, hh, vv, ff = bf.decode_rkg(path)
        return np.array([int(round(ff[f][2] * 7)) if f < len(ff) else 0 for f in range(R0, R1 + 1)], np.int8)

    seeds = [sticks_of(p) for p in [a.base] + a.seed]
    pop = np.zeros((n, L), np.int8)
    for i in range(n):
        s = seeds[i % len(seeds)].copy()
        if i >= len(seeds):          # mutated copies
            for _ in range(rng.integers(1, 6)):
                k = rng.integers(a.freeze_until - R0 if a.freeze_until > R0 else 0, (a.freeze_from - R0) if a.freeze_from > 0 else L)
                s[k] = np.clip(s[k] + rng.integers(-3, 4), -7, 7)
        pop[i] = s
    frozen = max(0, a.freeze_until - R0)
    frozen_vals = seeds[0][:frozen].copy()
    tail_from = (a.freeze_from - R0) if a.freeze_from > 0 else L          # index of the first frozen tail row
    tail_vals = seeds[0][tail_from:].copy() if tail_from < L else None
    if tail_vals is not None:
        pop[:, tail_from:] = tail_vals

    nr = a.need_row - R0
    nlo = np.arange(0)

    def evaluate(pop):
        eng.copy([0] * n, list(range(1, n + 1)))
        z = lambda dt=cp.int32: cp.zeros(n, dt)
        air, zero, grd, wall, drift_v, dirn, keep_def, gapv = z(), z(), z(), z(), z(), z(), cp.zeros(n, cp.float32), z()
        hang = z()
        zero2 = z()
        cdrift = z()
        first2 = cp.full(n, 99999, cp.int32)
        stay_dy, stay_nw = z(), z()
        wheels_sum = z()
        chs_end = cp.zeros(n, cp.float32)
        best_chs = cp.zeros(n, cp.float32)
        first570 = cp.full(n, 9999, cp.int32)
        stk_all = cp.asarray(pop.astype(np.float32) / 7.0)
        for k in range(L):
            f = R0 + k
            eng.step(1, n, make_inputs(cp.full(n, int(base_btn[k]), cp.int32), cp.full(n, int(base_trk[k]), cp.int32), stk_all[:, k], cp.zeros(n, cp.float32)))
            rows = eng.rows(1, n, f + 1)
            fl = rows[:, COL["flags"]].astype(cp.int64)
            airb = ((fl & 4) == 0).astype(cp.int32)
            if f >= a.air_from:
                air += airb
            if a.zero_rows[0] <= f <= a.zero_rows[1]:
                zero += airb
            if a.zero2_rows is not None and a.zero2_rows[0] <= f <= a.zero2_rows[1]:
                zero2 += airb
            if a.ground_rows[0] <= f <= a.ground_rows[1]:
                grd += airb
            wall += ((((fl >> 10) & 1) != 0) | (((fl >> 14) & 1) != 0)).astype(cp.int32)
            if a.hang_rows is not None and a.hang_rows[0] <= f <= a.hang_rows[1]:
                wh = rows[:, 118]
                hang += (wh > a.hang_max).astype(cp.int32)
                wheels_sum += wh.astype(cp.int32)
            ds = rows[:, COL["driftState"]]
            if a.counter_rows is not None and a.counter_rows[0] <= f <= a.counter_rows[1]:
                cdrift += (rows[:, COL["hopStickX"]] != 1).astype(cp.int32)
            if f <= a.drift_until:
                drift_v += (ds < 1).astype(cp.int32)
                dirn += (rows[:, COL["hopStickX"]] != -1).astype(cp.int32)
            comp = rows[:, COL["completion"]]
            comp_last = comp
            keep_def += cp.maximum(Rp["comp"][f] - a.keepup - comp, 0.0)
            px, pz = rows[:, COL["px"]], rows[:, COL["pz"]]
            lo = max(0, f - 14)
            d2 = (px[:, None] - Rp["px"][lo:f + 15][None, :]) ** 2 + (pz[:, None] - Rp["pz"][lo:f + 15][None, :]) ** 2
            gapv += (d2.min(axis=1) > a.max_gap ** 2).astype(cp.int32)
            if a.stay_rows is not None and a.stay_rows[0] <= f <= a.stay_rows[1]:
                kk = d2.argmin(axis=1)
                py_ref = Rp["py"][lo:f + 15][kk]
                stay_dy += (cp.abs(rows[:, COL["py"]] - py_ref) > a.stay_dy).astype(cp.int32)
                stay_nw += (rows[:, 118] < 0.5).astype(cp.int32)
            chs = cp.minimum(rows[:, COL["mtCharge"]], 270.0) + rows[:, SMT]
            first570 = cp.where((chs >= a.need_chs - 0.5) & (first570 == 9999), f, first570)
            if a.second_from is not None and f >= a.second_from:
                first2 = cp.where((chs >= a.need_chs - 0.5) & (first2 == 99999), f, first2)
            if f == a.need_row:
                chs_end = chs
        cost = (a.w_charge * cp.maximum(a.need_chs - chs_end, 0.0) + 400.0 * wall + 400.0 * drift_v + 400.0 * dirn
                + 200.0 * cp.maximum(zero - a.zero_cap, 0) + 300.0 * cp.maximum(zero2 - a.zero2_cap, 0) + a.w_counter * cdrift + a.w_final * (float(Rp["comp"][R1]) - comp_last) + (a.w_second * (cp.minimum(first2, a.to_row + 40) - a.second_from).astype(cp.float32) if a.second_from is not None else 0.0) + 300.0 * grd + 20000.0 * keep_def + 20.0 * gapv + a.w_air * air
                + 150.0 * hang + 150.0 * stay_dy + 150.0 * cp.maximum(stay_nw - a.stay_nowheel, 0))
        evaluate.hang = cp.asnumpy(hang)
        evaluate.first2 = cp.asnumpy(first2)
        evaluate.stay = cp.asnumpy(stay_dy) + cp.asnumpy(cp.maximum(stay_nw - a.stay_nowheel, 0))
        return cp.asnumpy(cost), cp.asnumpy(chs_end), cp.asnumpy(air), cp.asnumpy(zero), cp.asnumpy(first570)

    def report(g, cost, chs_end, air, zero, f570):
        i = int(np.argmin(cost))
        print(f"gen {g:3d}: best cost {cost[i]:9.1f} | charge at web {a.need_row + 2}: {chs_end[i]:5.0f}/{a.need_chs:.0f} | SMT charged at web "
              f"{(f570[i] + 2) if f570[i] < 9999 else '-'} | airborne {air[i]} | no-wheel in {a.zero_rows}: {zero[i]} | "
              f"2nd SMT web {(int(evaluate.first2[i]) + 2) if evaluate.first2[i] < 99999 else '-'} | hang-off breaks {int(evaluate.hang[i])} | off-road frames {int(evaluate.stay[i])} | valid {int((cost < 400).sum())}/{n} [{time.time() - t0:.0f}s]", flush=True)

    t0 = time.time()
    cost, chs_end, air, zero, f570 = evaluate(pop)
    report(0, cost, chs_end, air, zero, f570)
    for g in range(1, a.gens + 1):
        order = np.argsort(cost)
        ne = max(2, int(a.elite * n))
        new = np.zeros_like(pop)
        new[:ne] = pop[order[:ne]]
        half = max(ne + 1, n // 2)
        for i in range(ne, n):
            t1 = order[rng.integers(0, half, 2)].min()     # tournament among the better half
            t2 = order[rng.integers(0, half, 2)].min()
            ch_ = pop[t1].copy()
            op = rng.random()
            if op < 0.35:                                   # crossover
                p2 = pop[t2]
                if rng.random() < 0.5:
                    cut = rng.integers(1, L)
                    ch_[cut:] = p2[cut:]
                else:
                    c1, c2 = sorted(rng.integers(0, L, 2))
                    ch_[c1:c2] = p2[c1:c2]
            if rng.random() < 0.5:                          # point mutations
                for _ in range(rng.integers(1, 5)):
                    k = rng.integers(frozen, tail_from)
                    r_ = rng.random()
                    ch_[k] = np.clip(ch_[k] + rng.integers(-2, 3), -7, 7) if r_ < 0.6 else rng.integers(-7, 8)
            if rng.random() < 0.3:                          # block shift: move a stretch one frame earlier / later
                s0 = rng.integers(frozen, max(frozen + 1, tail_from - 2))
                s1 = rng.integers(s0 + 1, min(tail_from, s0 + 60) if tail_from > s0 + 1 else s0 + 2)
                if rng.random() < 0.5:                      # earlier: drop ch_[s0], shift left, repeat the last value
                    ch_[s0:s1 - 1] = ch_[s0 + 1:s1]
                else:                                       # later: duplicate ch_[s0], shift right
                    ch_[s0 + 1:s1] = ch_[s0:s1 - 1]
            if rng.random() < 0.3:                          # a run of +3 frames (the +5 charge) inserted
                s0 = rng.integers(frozen, max(frozen + 1, tail_from - 4))
                ch_[s0:min(tail_from, s0 + rng.integers(1, 5))] = 3
            ch_[:frozen] = frozen_vals
            if tail_vals is not None:
                ch_[tail_from:] = tail_vals
            new[i] = ch_
        pop = new
        cost, chs_end, air, zero, f570 = evaluate(pop)
        if g % 5 == 0 or g == a.gens:
            report(g, cost, chs_end, air, zero, f570)
        if int(f570[np.argmin(cost)]) <= a.need_row and cost.min() < 400 and g > 20 and g % 5 == 0:
            pass

    order = np.argsort(cost)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    seen, wrote = set(), 0
    for i in order:
        key = pop[i].tobytes()
        if key in seen:
            continue
        seen.add(key)
        out = list(fr)
        for k in range(L):
            b, t, sx, sy = out[R0 + k]
            out[R0 + k] = (b, t, pop[i][k] / 7.0, sy)
        path = f"{a.out}_{wrote}.rkg"
        open(path, "wb").write(bf.encode_rkg(c, ch, v, out, 0))
        print(f"candidate {wrote}: cost {cost[i]:.1f} charge {chs_end[i]:.0f} SMT at web {(f570[i] + 2) if f570[i] < 9999 else '-'} "
              f"airborne {air[i]} no-wheel {zero[i]} -> {path}", flush=True)
        wrote += 1
        if wrote >= 8:
            break
    print("done", flush=True)


if __name__ == "__main__":
    main()
