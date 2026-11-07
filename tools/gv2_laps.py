#!/usr/bin/env python3
"""Lap-line crossings of GV2 CPU replay dumps, compared with the first dump (the reference).

For each dump: the sub-frame row where race completion reaches 2.0, 3.0 and 4.0 (L1 line, L2 line, finish) and the
difference in frames from the reference, then frames ahead / lateral offset / EV at a few rows around the lap 2 entry
and the L2 hit.

    python tools/gv2_laps.py runs/gv2/gv2_27818.csv cand_cpu.csv ...
"""
import sys

import gv2_common as gv2

LINES = (2.0, 3.0, 4.0)
CHECK_ROWS = (976, 1000, 1396, 1398, 1420)


def lap_crossings(rows):
    completion = [float(r["completion"]) for r in rows]
    # from row 900 (the ultra crosses lines backwards before that), skipping jumps of half a lap or more
    return [gv2.line_crossing(completion, line, 900, require_rise=True, max_jump=0.5) for line in LINES]


def main():
    reference = gv2.load_dump(sys.argv[1])
    reference_path = gv2.path_of_dump(reference)
    reference_crossings = lap_crossings(reference)
    for path in sys.argv[1:]:
        rows = gv2.load_dump(path)
        laps = " | ".join(f"L{k + 1} line {x:8.2f} ({x - y:+.2f}f)" for k, (x, y) in enumerate(zip(lap_crossings(rows), reference_crossings)))
        checks = ""
        for row in CHECK_ROWS:
            if row < len(rows):
                x, z = gv2.position_xz(rows[row])
                ahead, lateral = gv2.progress_on_path(x, z, row, reference_path, look_back=25, look_ahead=24)
                checks += f" | @{row} ahead {ahead:+.2f} lat {lateral:+.0f} ev {gv2.horizontal_ev(rows[row]):.1f}"
        print(f"{path}: {laps}{checks} | rows {len(rows)}")


if __name__ == "__main__":
    main()
