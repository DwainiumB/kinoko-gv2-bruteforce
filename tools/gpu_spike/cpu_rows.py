"""Print selected CPU state columns around a frame range (debug helper for GPU mismatches)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
from brute_force import decode_rkg  # noqa: E402
from kinoko_search import KinokoSearch  # noqa: E402

first, last = int(sys.argv[1]), int(sys.argv[2])
cols = sys.argv[3].split(",")
fr = decode_rkg(os.path.join(ROOT, "samples", "tracks", "luigi-circuit", "ghosts", "tas", "1142.rkg"))[3]
r = KinokoSearch()
idx = [r.cols.index(c) for c in cols]
for i in range(last + 1):
    row = r.step(fr[i][0], fr[i][2], fr[i][3], fr[i][1])
    if i >= first:
        print(i, fr[i], " ".join(f"{c}={row[j]:.9g}" for c, j in zip(cols, idx)))
