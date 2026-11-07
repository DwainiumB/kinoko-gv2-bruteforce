#!/usr/bin/env python3
"""Lap-line crossings (sub-frame, from completion) and lap timer values of GV2 CPU dumps vs the 27.818 dump.

    python tools/gv2_laps.py runs/gv2/gv2_27818.csv cand_cpu.csv ...
"""
import csv, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from gv2_metrics import ev
from gv2_verify import path_ahead

def crossings(R):
    out = []
    comp = [float(r["completion"]) for r in R]
    for target in (2.0, 3.0, 4.0):
        i = next((k for k in range(900, len(R)) if comp[k] >= target and comp[k - 1] < target and comp[k] - comp[k - 1] < 0.5), None)
        out.append((i - 1) + (target - comp[i - 1]) / (comp[i] - comp[i - 1]) if i else float("nan"))
    return out

A = list(csv.DictReader(open(sys.argv[1])))
ca = crossings(A)
for p in sys.argv[1:]:
    B = list(csv.DictReader(open(p)))
    cb = crossings(B)
    s = " | ".join(f"L{k + 1} line {x:8.2f} ({x - y:+.2f}f)" for k, (x, y) in enumerate(zip(cb, ca)))
    extra = ""
    for r in (976, 1000, 1396, 1398, 1420):
        if r < len(B):
            ah, lat = path_ahead(B, r, A)
            extra += f" | @{r} ahead {ah:+.2f} lat {lat:+.0f} ev {ev(B[r]):.1f}"
    fin = next((i for i in range(len(B)) if int(B[i]["stage"]) > 2), None) if "stage" in B[0] else None
    print(f"{p}: {s}{extra} | rows {len(B)}")
