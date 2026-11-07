#!/usr/bin/env python3
"""Print how candidates move after each block hit, compared with the reference, from CPU replay dumps.

For each candidate dump (optionally `path@shift`, where shift = how many rows later the candidate's hit happens than
the reference's), finds its first block contact in the L1, L2 or L3 hit window and prints, at contact +0/10/20/30/40
rows: frames ahead of the reference (see gv2_common.ahead_of_reference_row), lateral offset, yaw, EV and speed.

    python tools/gv2_metrics.py runs/gv2/gv2_27818.csv cand_cpu.csv other_cpu.csv@1
"""
import sys

import gv2_common as gv2

HIT_WINDOWS = ((780, 900), (1340, 1460), (1890, 2010))   # rows searched for the L1, L2 and L3 block contact
ROWS_AFTER_CONTACT = (0, 10, 20, 30, 40)


def report(reference, candidate, label, shift):
    for first, end in HIT_WINDOWS:
        contact = gv2.first_contact_row(candidate, first, end)
        if contact is None or not (first <= contact - shift < end + 600):
            continue
        lines = [f"{label}@{shift} contact row {contact}"]
        for after in ROWS_AFTER_CONTACT:
            row = contact + after
            reference_row = row - shift
            if reference_row + 1 < len(reference):
                ahead, lateral = gv2.ahead_of_reference_row(candidate[row], reference[reference_row], reference[reference_row + 1])
            else:
                ahead, lateral = float("nan"), 0
            lines.append(f"+{after}: ahead {ahead:+.3f}f lat {lateral:+6.1f} yaw {gv2.yaw_degrees(candidate[row]):8.2f} "
                         f"ev {gv2.horizontal_ev(candidate[row]):5.1f} sp {float(candidate[row]['speed']):5.1f}")
        print("\n   ".join(lines))
        return


def main():
    reference = gv2.load_dump(sys.argv[1])
    for spec in sys.argv[2:]:
        label, shift = spec.split("@") if "@" in spec else (spec, "0")
        candidate = gv2.load_dump(label) if label != "self" else reference
        report(reference, candidate, label, int(shift))


if __name__ == "__main__":
    main()
