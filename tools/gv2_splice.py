#!/usr/bin/env python3
"""Splice sweep: a candidate's inputs before row S, then the reference's inputs taken d rows later (shifted by d).

Every (S, d) pair in the --s and --d ranges runs in one GPU batch, alongside the reference itself. Each splice is
scored on its L1-line crossing (sub-frame, from race completion) and on its state at --at-rows: frames ahead of the
reference path, lateral offset, EV and speed. The best --top are printed (and written with --out).

Use it to find where a new hit's run can hand over to the reference's inputs, e.g. after the superhops.

    python tools/gv2_splice.py --cand runs/gv2/gv2_L1hit_E.rkg --s 847 976 --d -3 1 --out runs/gv2/spliceE
"""
import argparse

import numpy as np

import gv2_common as gv2
import brute_force as bf  # noqa: E402  (gv2_common puts tools/ on sys.path)

cp, Engine, make_inputs, COLUMN = gv2.gpu_modules()

L1_LINE = 2.0                 # race completion at the lap 1 line
CROSSINGS_AFTER_ROW = 900     # ignore completion changes before this row (the ultra crosses lines backwards earlier)
NOT_CROSSED = 1e9             # sort key of a splice that never reaches the line


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cand", required=True, help="run whose inputs are used before row S")
    ap.add_argument("--ref", default=gv2.REFERENCE_GHOST, help="reference run (default: the 27.818)")
    ap.add_argument("--ref-dump", default=gv2.REFERENCE_DUMP, help="CPU replay dump of the reference (for the path)")
    ap.add_argument("--s", type=int, nargs=2, default=[847, 976], help="range of splice rows S (inclusive)")
    ap.add_argument("--d", type=int, nargs=2, default=[-3, 1], help="range of shifts d (inclusive)")
    ap.add_argument("--to-row", type=int, default=1060, help="last simulated row")
    ap.add_argument("--at-rows", type=int, nargs="+", default=[976, 1000, 1050], help="rows where the state is reported")
    ap.add_argument("--max-lat", type=float, default=1e9, help="rank splices off the ref line by more than this at the first --at-rows row last")
    ap.add_argument("--rank-comp", action="store_true", help="rank by race completion at the last --at-rows row (the ultra shortcut), then by the L1 line")
    ap.add_argument("--top", type=int, default=12, help="how many splices to print / write")
    ap.add_argument("--out", default=None, help="write the best --top splices as <out>_<k>.rkg")
    a = ap.parse_args()

    course, character, vehicle, candidate = bf.decode_rkg(a.cand)
    reference = list(bf.decode_rkg(a.ref)[3])
    candidate = list(candidate)
    pairs = [(s, d) for s in range(a.s[0], a.s[1] + 1) for d in range(a.d[0], a.d[1] + 1)]
    races = len(pairs) + 1                       # race 0 = the reference itself
    last_row = a.to_row

    def spliced(splice_row, shift):
        frames = list(candidate[:splice_row])
        for row in range(splice_row, last_row + 1):
            source = row + shift
            frames.append(reference[source] if 0 <= source < len(reference) else gv2.NO_INPUT)
        return frames

    runs = [list(reference[:last_row + 1])] + [spliced(s, d) for s, d in pairs]
    buttons, tricks, stick_x, stick_y = (cp.asarray(np.array([[f[field] for f in run[:last_row + 1]] for run in runs], dtype))
                                         for field, dtype in ((0, np.int32), (1, np.int32), (2, np.float32), (3, np.float32)))

    engine = Engine(races + 1, course=course, character=character, vehicle=vehicle)
    engine.clone_template(1, races)
    previous_completion = cp.zeros(races, cp.float32)
    crossing = cp.full(races, cp.nan, cp.float32)
    snapshots = {}                               # row -> numpy (races, 6): x, z, evx, evz, speed, completion
    for row in range(last_row + 1):
        engine.step(1, races, make_inputs(buttons[:, row], tricks[:, row], stick_x[:, row], stick_y[:, row]))
        state = engine.rows(1, races, row + 1)
        completion = state[:, COLUMN["completion"]].astype(cp.float32)
        crosses = (completion >= L1_LINE) & (previous_completion < L1_LINE) & cp.isnan(crossing) & (row > CROSSINGS_AFTER_ROW)
        crossing = cp.where(crosses, (row - 1) + (L1_LINE - previous_completion) / cp.maximum(completion - previous_completion, 1e-6), crossing)
        previous_completion = completion
        if row in a.at_rows:
            snapshots[row] = cp.asnumpy(state[:, [COLUMN["px"], COLUMN["pz"], COLUMN["evx"], COLUMN["evz"], COLUMN["speed"], COLUMN["completion"]]])
    crossing = cp.asnumpy(crossing)

    reference_path = gv2.path_of_dump(gv2.load_dump(a.ref_dump), last_row + 60)
    results = []
    for i in range(races):
        result = {"cross": crossing[i]}
        for row in a.at_rows:
            x, z, evx, evz, speed, _ = snapshots[row][i]
            ahead, lateral = gv2.progress_on_path(x, z, row, reference_path, look_back=40, look_ahead=40)
            result[row] = (ahead, lateral, float(np.hypot(evx, evz)), float(speed))
        results.append(result)
    reference_crossing = results[0]["cross"]

    def describe(result):
        text = f"L1 line {result['cross']:.2f} ({result['cross'] - reference_crossing:+.2f}f)"
        for row in a.at_rows:
            ahead, lateral, ev, speed = result[row]
            text += f" | @{row} ahead {ahead:+.2f}f lat {lateral:+6.1f} ev {ev:4.1f} sp {speed:5.1f}"
        return text

    def crossing_key(i):
        return results[i]["cross"] if not np.isnan(results[i]["cross"]) else NOT_CROSSED

    last_at_row = a.at_rows[-1]
    if a.rank_comp:
        def rank_key(i):
            return (-round(float(snapshots[last_at_row][i][5]), 3), crossing_key(i))
    else:
        def rank_key(i):
            off_line = abs(results[i][a.at_rows[0]][1]) >= a.max_lat
            return crossing_key(i) + (1000.0 if off_line else 0.0)

    print(f"reference: {describe(results[0])}")
    ranked = sorted(range(1, races), key=rank_key)
    for rank, i in enumerate(ranked[:a.top]):
        s, d = pairs[i - 1]
        print(f"S={s} d={d:+d}: {describe(results[i])} | comp@{last_at_row} {snapshots[last_at_row][i][5]:.4f} "
              f"(ref {snapshots[last_at_row][0][5]:.4f})")
        if a.out:
            open(f"{a.out}_{rank}.rkg", "wb").write(bf.encode_rkg(course, character, vehicle, runs[i], 0))
    print("best L1 line among all:", min((results[i]["cross"], pairs[i - 1]) for i in range(1, races) if not np.isnan(results[i]["cross"])))


if __name__ == "__main__":
    main()
