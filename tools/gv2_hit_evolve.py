#!/usr/bin/env python3
"""GV2 (course 25) lap-1 fast block hit search: a GV2 copy of tools/evolve.py with sam's (fable5mkw) settings.

A genome is a stick X and a stick Y value (-7..+7) per row of the edit window (default rows 771..846 = input
frames 600..675, the run-up to the block contact at row ~846). Buttons/trick come from the base run and are fixed;
every row from --freeze-from on (the B release / hit) keeps the base run's inputs. The population starts at the base
run and mutates with a SMALL edit budget, mostly vertical stick (--p-y).

Cost (lower = better), everything measured against the reference (the 27.818) at the SAME dump row:
    - w_fwd  * ahead at contact+20 / +30   (along-track progress on the reference path, in frames)
    - w_ev   * min(EV at row 850, ev_cap)   (horizontal external velocity after the hit; 27.818: ~44)
    - w_yaw  * (yaw at contact-2 - reference yaw)   (higher yaw = "right": L2 table, -113.2 beats -114.4)
    + w_pace * sum over pre-contact rows of max(|ahead| - pace_tol, 0)   (sam's pace attractor)
    + w_edit * edits beyond --budget   + 50 per edit (tie-break toward few edits)
    + 1000 if (--need-drift) the drift ends before contact, or the contact row falls outside [--contact-lo, --contact-hi]

    python tools/gv2_hit_evolve.py --base PENDING.rkg --ref 27.818.rkg --out runs/gv2/evoA --gens 150
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
from evolve import COL  # noqa: E402

G = "samples/tracks/ghost-valley-2/ghosts/"


def yaw_deg(rows):
    qx, qy, qz, qw = (rows[:, COL[k]] for k in ("qx", "qy", "qz", "qw"))
    return cp.degrees(cp.arctan2(2 * (qx * qz + qw * qy), 1 - 2 * (qx * qx + qy * qy)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=G + "rGV2_22.000_slimpanda_L1_with_L3_movement_PENDING.rkg")
    ap.add_argument("--ref", default=G + "rGV2_27.818_slimpanda_best.rkg")
    ap.add_argument("--seed", action="append", default=[], help="extra runs whose window sticks seed part of the population")
    ap.add_argument("--from-row", type=int, default=771, help="first edited row (input frame = row - 171)")
    ap.add_argument("--freeze-from", type=int, default=847, help="rows from here on keep the base inputs (B release / hit)")
    ap.add_argument("--contact-lo", type=int, default=840)
    ap.add_argument("--contact-hi", type=int, default=852)
    ap.add_argument("--ref-contact", type=int, default=846)
    ap.add_argument("--fwd-after", type=int, nargs="+", default=[20, 30], help="score ahead at ref-contact + these rows")
    ap.add_argument("--ev-row", type=int, default=850)
    ap.add_argument("--pop", type=int, default=2048)
    ap.add_argument("--gens", type=int, default=150)
    ap.add_argument("--elite", type=float, default=0.08)
    ap.add_argument("--budget", type=int, default=10, help="edits (changed stick values vs base) allowed without penalty")
    ap.add_argument("--p-y", type=float, default=0.8, help="probability a mutation touches stick Y (else stick X)")
    ap.add_argument("--w-fwd", type=float, default=100.0)
    ap.add_argument("--w-ev", type=float, default=3.0)
    ap.add_argument("--ev-cap", type=float, default=50.0)
    ap.add_argument("--w-yaw", type=float, default=5.0)
    ap.add_argument("--w-pace", type=float, default=200.0)
    ap.add_argument("--pace-tol", type=float, default=0.25)
    ap.add_argument("--w-edit", type=float, default=40.0)
    ap.add_argument("--w-each", type=float, default=0.5)
    ap.add_argument("--max-lat", type=float, default=60.0, help="pre-contact lateral offset from the ref path above this costs 20/row")
    ap.add_argument("--need-drift", action="store_true", help="1000 if driftState < 1 on any pre-contact row (off: no drift in this window)")
    ap.add_argument("--btn-from", default=None, help="take the window buttons from this run instead of the base (e.g. the 27.818: 11 vs 3)")
    ap.add_argument("--w-postlat", type=float, default=0.0, help="cost per unit of lateral offset from the ref path beyond --postlat-tol at the --fwd-after rows (keeps the line for the superhops)")
    ap.add_argument("--postlat-tol", type=float, default=30.0)
    ap.add_argument("--yaw-contact-target", type=float, default=None, help="target yaw (deg) at the contact row, e.g. A's -114.7")
    ap.add_argument("--w-yaw-contact", type=float, default=0.0, help="cost per degree of |yaw at contact - target| beyond --yaw-contact-tol")
    ap.add_argument("--yaw-contact-tol", type=float, default=1.0)
    ap.add_argument("--seed-rng", type=int, default=1)
    ap.add_argument("--time-limit", type=float, default=1700.0, help="stop after this many seconds and write the candidates")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed_rng)

    c, ch, v, fr = bf.decode_rkg(a.base)
    fr = list(fr)
    R0, RF = a.from_row, a.freeze_from
    W = RF - R0                                   # editable rows
    R1 = a.ref_contact + max(a.fwd_after) + 2      # last simulated row
    n = a.pop

    # reference path
    cr = bf.decode_rkg(a.ref)
    rfr = list(cr[3])
    NR = R1 + 40
    ref = np.zeros((NR, 4), np.float32)          # px, pz, yaw, completion
    er = Engine(2, course=cr[0], character=cr[1], vehicle=cr[2])
    er.clone_template(0, 1)
    for f in range(NR):
        b, t, sx, sy = rfr[f]
        er.step(0, 1, make_inputs(cp.asarray([b], cp.int32), cp.asarray([t], cp.int32), cp.asarray([sx], cp.float32), cp.asarray([sy], cp.float32)))
        r = er.rows(0, 1, f + 1)
        ref[f] = [float(r[0, COL["px"]]), float(r[0, COL["pz"]]), float(yaw_deg(r)[0]), float(r[0, COL["completion"]])]
    del er
    RP = cp.asarray(ref)

    def ahead_of(rows, f):
        """along-track position on the ref path minus f, in rows (frames); plus |lateral| offset."""
        lo, hi = max(0, f - 25), min(NR - 1, f + 25)
        px, pz = rows[:, COL["px"]], rows[:, COL["pz"]]
        seg = RP[lo:hi]
        d2 = (px[:, None] - seg[None, :, 0]) ** 2 + (pz[:, None] - seg[None, :, 1]) ** 2
        k = cp.minimum(d2.argmin(axis=1), hi - lo - 2)
        x0, z0 = seg[k, 0], seg[k, 1]
        x1, z1 = RP[lo + k + 1, 0], RP[lo + k + 1, 1]
        dx, dz = x1 - x0, z1 - z0
        s2 = cp.maximum(dx * dx + dz * dz, 1e-6)
        t = ((px - x0) * dx + (pz - z0) * dz) / s2
        lat = cp.abs((px - x0) * dz - (pz - z0) * dx) / cp.sqrt(s2)
        return (lo + k).astype(cp.float32) + t - f, lat

    # engine: slot 0 = state after row R0-1, slots 1..n = population
    eng = Engine(n + 2, course=c, character=ch, vehicle=v)
    eng.clone_template(0, 1)
    for f in range(R0):
        b, t, sx, sy = fr[f]
        eng.step(0, 1, make_inputs(cp.asarray([b], cp.int32), cp.asarray([t], cp.int32), cp.asarray([sx], cp.float32), cp.asarray([sy], cp.float32)))
    if a.btn_from:
        bfr = list(bf.decode_rkg(a.btn_from)[3])
        for f in range(R0, RF):
            fr[f] = (bfr[f][0],) + tuple(fr[f][1:])
    btn = np.array([fr[f][0] for f in range(R0, R1 + 1)], np.int32)
    trk = np.array([fr[f][1] for f in range(R0, R1 + 1)], np.int32)
    tail_sx = np.array([fr[f][2] for f in range(RF, R1 + 1)], np.float32)
    tail_sy = np.array([fr[f][3] for f in range(RF, R1 + 1)], np.float32)

    def window_of(frames):
        return np.array([[int(round(frames[f][2] * 7)), int(round(frames[f][3] * 7))] for f in range(R0, RF)], np.int8)

    base_g = window_of(fr)                         # (W, 2)
    seeds = [base_g] + [window_of(list(bf.decode_rkg(p)[3])) for p in a.seed]

    def mutate(g, k_edits):
        for _ in range(k_edits):
            k = rng.integers(0, W)
            ax = 1 if rng.random() < a.p_y else 0
            r_ = rng.random()
            if r_ < 0.45:
                g[k, ax] = np.clip(g[k, ax] + rng.choice([-2, -1, 1, 2]), -7, 7)
            elif r_ < 0.75:
                g[k, ax] = rng.integers(-7, 8)
            else:                                   # revert toward the base (keeps the edit count small)
                g[k, ax] = base_g[k, ax]
        return g

    pop = np.zeros((n, W, 2), np.int8)
    for i in range(n):
        s = seeds[i % len(seeds)].copy()
        if i >= len(seeds):
            s = mutate(s, int(rng.integers(1, 4)))
        pop[i] = s

    fwd_rows = [a.ref_contact + d for d in a.fwd_after]

    def evaluate(pop):
        eng.copy([0] * n, list(range(1, n + 1)))
        sx_all = cp.asarray(pop[:, :, 0].astype(np.float32) / 7.0)
        sy_all = cp.asarray(pop[:, :, 1].astype(np.float32) / 7.0)
        pace = cp.zeros(n, cp.float32)
        latpen = cp.zeros(n, cp.float32)
        contact = cp.full(n, 9999, cp.int32)
        drift_lost = cp.zeros(n, cp.int32)
        fwd = cp.zeros(n, cp.float32)
        ev = cp.zeros(n, cp.float32)
        yaw_d = cp.zeros(n, cp.float32)
        postlat = cp.zeros(n, cp.float32)
        yaw_c = cp.zeros(n, cp.float32)
        info = {}
        for f in range(R0, R1 + 1):
            k = f - R0
            if f < RF:
                sx, sy = sx_all[:, k], sy_all[:, k]
            else:
                sx, sy = cp.full(n, float(tail_sx[f - RF]), cp.float32), cp.full(n, float(tail_sy[f - RF]), cp.float32)
            eng.step(1, n, make_inputs(cp.full(n, int(btn[k]), cp.int32), cp.full(n, int(trk[k]), cp.int32), sx, sy))
            rows = eng.rows(1, n, f + 1)
            fl = rows[:, COL["flags"]].astype(cp.int64)
            hit = ((fl & 0x400) != 0) & (contact == 9999) & (f >= a.contact_lo - 6)
            contact = cp.where(hit, f, contact)
            yaw_c = cp.where(hit, yaw_deg(rows).astype(cp.float32), yaw_c)
            if f < a.ref_contact - 1:
                ah, lat = ahead_of(rows, f)
                pace += cp.maximum(cp.abs(ah) - a.pace_tol, 0.0)
                latpen += (lat > a.max_lat).astype(cp.float32)
                drift_lost += (rows[:, COL["driftState"]] < 1).astype(cp.int32)
            if f == a.ref_contact - 2:
                yaw_d = yaw_deg(rows) - float(ref[f, 2])
                info["ah_pre"] = ahead_of(rows, f)[0]
            if f == a.ev_row:
                ev = cp.hypot(rows[:, COL["evx"]], rows[:, COL["evz"]])
            if f in fwd_rows:
                ah_f, lat_f = ahead_of(rows, f)
                fwd += ah_f / len(fwd_rows)
                postlat += cp.maximum(lat_f - a.postlat_tol, 0.0) / len(fwd_rows)
                if f == fwd_rows[0]:
                    info["fwd20"] = ahead_of(rows, f)[0]
        edits = cp.asarray((pop != base_g[None]).sum(axis=(1, 2)).astype(np.float32))
        bad_contact = (contact < a.contact_lo) | (contact > a.contact_hi)
        yc_pen = cp.maximum(cp.abs(yaw_c - a.yaw_contact_target) - a.yaw_contact_tol, 0.0) if a.yaw_contact_target is not None else cp.zeros(n, cp.float32)
        cost = (a.w_yaw_contact * yc_pen - a.w_fwd * fwd - a.w_ev * cp.minimum(ev, a.ev_cap) - a.w_yaw * yaw_d + a.w_pace * pace + 20.0 * latpen
                + a.w_postlat * postlat + a.w_edit * cp.maximum(edits - a.budget, 0) + a.w_each * edits + 1000.0 * bad_contact + (1000.0 * (drift_lost > 0) if a.need_drift else 0.0))
        return {"cost": cp.asnumpy(cost), "fwd": cp.asnumpy(fwd), "fwd20": cp.asnumpy(info["fwd20"]), "ev": cp.asnumpy(ev),
                "yaw": cp.asnumpy(yaw_d), "pace": cp.asnumpy(pace), "contact": cp.asnumpy(contact), "edits": cp.asnumpy(edits),
                "ah_pre": cp.asnumpy(info["ah_pre"]), "drift": cp.asnumpy(drift_lost), "postlat": cp.asnumpy(postlat), "yawc": cp.asnumpy(yaw_c)}

    def line(m, i):
        return (f"cost {m['cost'][i]:8.1f} | fwd@+20 {m['fwd20'][i]:+.3f}f mean {m['fwd'][i]:+.3f}f | EV@{a.ev_row} {m['ev'][i]:5.1f} | "
                f"yaw-ref@{a.ref_contact - 2} {m['yaw'][i]:+.2f} | ahead@{a.ref_contact - 2} {m['ah_pre'][i]:+.3f}f | pace {m['pace'][i]:.2f} | "
                f"postlat {m['postlat'][i]:.0f} | yaw@contact {m['yawc'][i]:.1f} | contact row {m['contact'][i]} | edits {int(m['edits'][i])}")

    t0 = time.time()
    m = evaluate(pop)
    print(f"base: {line(m, 0)}", flush=True)
    print(f"gen   0: {line(m, int(np.argmin(m['cost'])))} [{time.time() - t0:.0f}s]", flush=True)
    g = 0
    for g in range(1, a.gens + 1):
        cost = m["cost"]
        order = np.argsort(cost)
        ne = max(2, int(a.elite * n))
        new = np.empty_like(pop)
        new[:ne] = pop[order[:ne]]
        half = max(ne + 1, n // 3)
        for i in range(ne, n):
            p1 = order[rng.integers(0, half, 2)].min()
            ch_ = pop[p1].copy()
            if rng.random() < 0.3:                  # crossover with another good one (contiguous block)
                p2 = order[rng.integers(0, half, 2)].min()
                c1, c2 = sorted(rng.integers(0, W, 2))
                ch_[c1:c2 + 1] = pop[p2][c1:c2 + 1]
            ch_ = mutate(ch_, int(rng.integers(1, 3)))
            new[i] = ch_
        pop = new
        m = evaluate(pop)
        if g % 5 == 0 or g == a.gens:
            i = int(np.argmin(m["cost"]))
            ok = (m["cost"] < 500)
            print(f"gen {g:3d}: {line(m, i)} | valid {int(ok.sum())}/{n} | best fwd@+20 among valid "
                  f"{m['fwd20'][ok].max() if ok.any() else float('nan'):+.3f}f [{time.time() - t0:.0f}s]", flush=True)
        if time.time() - t0 > a.time_limit:
            print(f"time limit reached at gen {g}", flush=True)
            break

    order = np.argsort(m["cost"])
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    seen, wrote = set(), 0
    for i in order:
        key = pop[i].tobytes()
        if key in seen:
            continue
        seen.add(key)
        out = list(fr)
        for k in range(W):
            b, t, _, _ = out[R0 + k]
            out[R0 + k] = (b, t, pop[i][k, 0] / 7.0, pop[i][k, 1] / 7.0)
        path = f"{a.out}_{wrote}.rkg"
        open(path, "wb").write(bf.encode_rkg(c, ch, v, out, 0))
        print(f"candidate {wrote}: {line(m, i)} -> {path}", flush=True)
        wrote += 1
        if wrote >= 6:
            break
    print("done", flush=True)


if __name__ == "__main__":
    main()
