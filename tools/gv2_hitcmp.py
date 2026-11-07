#!/usr/bin/env python3
"""Compare L1 fast-block-hit metrics of CPU dumps against the 27.818 dump (rows 830-880).

    python tools/gv2_hitcmp.py runs/gv2/gv2_27818.csv cand1.csv cand2.csv ...
contact = first row in [830, 880) with flags bit 0x400. ahead = along-track offset vs the reference at the SAME row, in frames."""
import sys
from gv2_metrics import load, yaw, ev, ahead

ref = load(sys.argv[1])
for p in sys.argv[1:]:
    B = load(p)
    c = next((i for i in range(830, 880) if int(B[i]['flags']) & 0x400), None)
    print(f"{p}: contact row {c} (input frame {c - 172 if c else '-'})")
    for k in (-2, 0, 2, 4, 10, 20, 30):
        r = 846 + k
        a, lat = ahead(B, r, ref, r)
        print(f"   row {r} (contact{k:+d}): ahead {a:+.3f}f lat {lat:+6.1f} yaw {yaw(B[r]):8.2f} ev {ev(B[r]):5.1f} "
              f"sp {float(B[r]['speed']):6.2f} comp {float(B[r]['completion']):.5f}")
