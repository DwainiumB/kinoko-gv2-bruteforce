#!/usr/bin/env python3
"""CPU replay-verify GV2 L1 hit candidates and write sam-format input-edit CSVs.

For each candidate .rkg: runs kinoko_host replay --dump, prints the hit metrics against the 27.818
dump (contact row, EV, yaw, ahead at contact+20/+30 on the 27.818 path), and writes <cand>.csv listing every changed
input frame against --base in sam's (fable5mkw) column format.

    python tools/gv2_verify.py --base PENDING.rkg runs/gv2/evoA_0.rkg [...]
input_frame = index in the rkg input stream (engine frame - 172); race_frame = input_frame - 240; time_s = race_frame / 59.94.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brute_force as bf  # noqa: E402
from kinoko_search import find_host_binary  # noqa: E402
from gv2_metrics import load, yaw, ev  # noqa: E402

ROOT = os.path.dirname(HERE)
G = os.path.join(ROOT, "samples/tracks/ghost-valley-2/ghosts/")
TRICK = {0: "none", 1: "up", 2: "down", 3: "left", 4: "right"}


def path_ahead(B, r, A):
    """along-track position of B[r] on A's path (nearest segment among rows r-25..r+25) minus r, plus signed lateral."""
    x, z = float(B[r]["px"]), float(B[r]["pz"])
    best = None
    for k in range(max(0, r - 25), min(len(A) - 1, r + 25)):
        x0, z0, x1, z1 = float(A[k]["px"]), float(A[k]["pz"]), float(A[k + 1]["px"]), float(A[k + 1]["pz"])
        d = (x - x0) ** 2 + (z - z0) ** 2
        if best is None or d < best[0]:
            best = (d, k, x0, z0, x1, z1)
    _, k, x0, z0, x1, z1 = best
    dx, dz = x1 - x0, z1 - z0
    s2 = max(dx * dx + dz * dz, 1e-6)
    t = ((x - x0) * dx + (z - z0) * dz) / s2
    lat = ((x - x0) * dz - (z - z0) * dx) / s2 ** 0.5
    return k + t - r, lat


def metrics(B, A):
    c = next((i for i in range(835, 860) if int(B[i]["flags"]) & 0x400), None)
    out = {"contact": c}
    for k in (20, 30):
        out[f"ahead+{k}"], out[f"lat+{k}"] = path_ahead(B, 846 + k, A)
    out["ev850"] = ev(B[850])
    out["ev_contact"] = ev(B[c]) if c else float("nan")
    out["yaw844"] = yaw(B[844])
    out["yaw_contact"] = yaw(B[c]) if c else float("nan")
    out["pre_ahead844"], out["pre_lat844"] = path_ahead(B, 844, A)
    return out


def fmt(m):
    return (f"contact row {m['contact']} (input {m['contact'] - 172 if m['contact'] else '-'}) | EV@contact {m['ev_contact']:.1f} "
            f"EV@850 {m['ev850']:.1f} | yaw@844 {m['yaw844']:.2f} @contact {m['yaw_contact']:.2f} | ahead@844 {m['pre_ahead844']:+.3f}f "
            f"lat {m['pre_lat844']:+.1f} | ahead+20 {m['ahead+20']:+.3f}f (lat {m['lat+20']:+.1f}) ahead+30 {m['ahead+30']:+.3f}f")


def edit_csv(base, cand, path, title):
    fb, fc = list(bf.decode_rkg(base)[3]), list(bf.decode_rkg(cand)[3])
    lines = [f"# {title}",
             "# input_frame = index in the rkg input stream (0 = first countdown frame); race_frame = input_frame - 240 (0 = timer start)",
             "# face bits: 1=A 2=B 4=item 8=drift; stick -7..7; only changed frames listed",
             "input_frame,race_frame,time_s,orig_face,new_face,orig_stick_x,new_stick_x,orig_stick_y,new_stick_y,orig_trick,new_trick"]
    n = 0
    for f in range(bf.COUNTDOWN_START_FRAME, min(len(fb), len(fc))):
        if fb[f] != fc[f]:
            i = f - bf.COUNTDOWN_START_FRAME
            rf = i - 240
            (b0, t0, x0, y0), (b1, t1, x1, y1) = fb[f], fc[f]
            lines.append(f"{i},{rf},{rf / 59.94:.3f},{b0},{b1},{round(x0 * 7)},{round(x1 * 7)},{round(y0 * 7)},{round(y1 * 7)},{TRICK.get(t0, t0)},{TRICK.get(t1, t1)}")
            n += 1
    open(path, "w").write("\n".join(lines) + "\n")
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=G + "rGV2_22.000_slimpanda_L1_with_L3_movement_PENDING.rkg")
    ap.add_argument("--ref-dump", default=os.path.join(ROOT, "runs/gv2/gv2_27818.csv"))
    ap.add_argument("--binary", default=find_host_binary())
    ap.add_argument("cands", nargs="+")
    a = ap.parse_args()
    A = load(a.ref_dump)
    print("27.818 :", fmt(metrics(A, A)))
    for p in a.cands:
        dump = os.path.splitext(p)[0] + "_cpu.csv"
        subprocess.run([a.binary, "replay", "--ghost", p, "--dump", dump], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        B = load(dump)
        m = metrics(B, A)
        n = edit_csv(a.base, p, os.path.splitext(p)[0] + "_edits.csv",
                     f"rGV2 L1 fast block hit candidate {os.path.basename(p)}; orig = {os.path.basename(a.base)}; {fmt(m)}")
        print(f"{os.path.basename(p)}: {fmt(m)} | {n} edited frames")


if __name__ == "__main__":
    main()
