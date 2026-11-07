#!/usr/bin/env python3
"""Compare the L1 fast block hit of CPU replay dumps with the reference dump, row by row around contact.

contact = first row in [830, 880) with the block-contact flag. At the reference's contact row 846 -2/0/+2/+4/+10/+20/+30
it prints frames ahead of the reference at the same row (gv2_common.ahead_of_reference_row), lateral offset, yaw, EV,
speed and race completion. The first file is the reference and is listed too.

    python tools/gv2_hitcmp.py runs/gv2/gv2_27818.csv cand1_cpu.csv cand2_cpu.csv
"""
import sys

import gv2_common as gv2

REFERENCE_CONTACT_ROW = 846
OFFSETS = (-2, 0, 2, 4, 10, 20, 30)


def main():
    reference = gv2.load_dump(sys.argv[1])
    for path in sys.argv[1:]:
        rows = gv2.load_dump(path)
        contact = gv2.first_contact_row(rows, 830, 880)
        print(f"{path}: contact row {contact} (input frame {gv2.input_frame_of_row(contact) if contact else '-'})")
        for offset in OFFSETS:
            row = REFERENCE_CONTACT_ROW + offset
            ahead, lateral = gv2.ahead_of_reference_row(rows[row], reference[row], reference[row + 1])
            print(f"   row {row} (contact{offset:+d}): ahead {ahead:+.3f}f lat {lateral:+6.1f} yaw {gv2.yaw_degrees(rows[row]):8.2f} "
                  f"ev {gv2.horizontal_ev(rows[row]):5.1f} sp {float(rows[row]['speed']):6.2f} comp {float(rows[row]['completion']):.5f}")


if __name__ == "__main__":
    main()
