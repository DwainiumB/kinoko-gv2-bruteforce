#!/usr/bin/env python3
"""Check that the GPU engine replays a ghost exactly like the CPU build.

Steps one GPU race with the ghost's inputs and compares position, rotation, EV, speed, completion and flags on every
row with a CPU replay dump of the same ghost. Prints the first 10 mismatches and the total; expect 0 before trusting
a GPU search on a track.

    python tools/gv2_gpu_parity.py ghost.rkg ghost_cpu.csv [rows]
"""
import csv
import sys

import gv2_common as gv2
import brute_force as bf  # noqa: E402  (gv2_common puts tools/ on sys.path)

cp, Engine, make_inputs, COLUMN = gv2.gpu_modules()
from gpu_engine import ROW_COLUMN_NAMES  # noqa: E402

COMPARED = ("px", "py", "pz", "qx", "qy", "qz", "qw", "evx", "evy", "evz", "speed", "completion", "flags")


def main():
    ghost, dump = sys.argv[1], sys.argv[2]
    row_limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    course, character, vehicle, frames = bf.decode_rkg(ghost)
    cpu_rows = list(csv.reader(open(dump)))[1:]
    rows = min(len(frames), len(cpu_rows), row_limit or 10**9)
    engine = Engine(2, course=course, character=character, vehicle=vehicle)
    engine.clone_template(0, 1)
    mismatches = 0
    for row in range(rows):
        gv2.step_single_race(engine, 0, frames[row])
        gpu = cp.asnumpy(engine.rows(0, 1, row + 1))[0]
        for name in COMPARED:
            gpu_value, cpu_value = float(gpu[COLUMN[name]]), float(cpu_rows[row][ROW_COLUMN_NAMES.index(name)])
            if gpu_value != cpu_value and not (abs(gpu_value - cpu_value) <= 1e-6 * max(1.0, abs(cpu_value))):
                if mismatches < 10:
                    print(f"MISMATCH frame {row} {name}: gpu {gpu_value!r} cpu {cpu_value!r}")
                mismatches += 1
    print(f"course {course} char {character} veh {vehicle}: compared {rows} frames, mismatching values {mismatches}")


if __name__ == "__main__":
    main()
