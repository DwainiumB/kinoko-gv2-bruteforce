#!/usr/bin/env python3
"""Check GV2 lap 1 hit candidates on the CPU build and write their input edits in sam's CSV format.

For each candidate .rkg this:
  1. replays it with `kinoko_host replay --dump` (writes <candidate>_cpu.csv),
  2. prints the hit metrics against the reference dump: contact row, EV at contact and at row 850, yaw two rows before
     contact and at contact, frames ahead and lateral offset at row 844 and at contact +20 / +30 on the reference path,
  3. writes <candidate>_edits.csv: every input frame that differs from --base, in sam's (fable5mkw) column format.

    python tools/gv2_verify.py runs/gv2/evoA_0.rkg runs/gv2/evoA_1.rkg
"""
import argparse
import os
import subprocess

import gv2_common as gv2
import brute_force as bf  # noqa: E402  (gv2_common puts tools/ on sys.path)
from kinoko_search import find_host_binary  # noqa: E402

REFERENCE_CONTACT_ROW = 846     # the 27.818's L1 contact row
PRE_CONTACT_ROW = 844
EV_ROW = 850


def path_ahead(rows, row, reference_path):
    """Frames ahead of the reference path and signed lateral offset of rows[row] (nearest point among row-25 .. row+24)."""
    x, z = gv2.position_xz(rows[row])
    return gv2.progress_on_path(x, z, row, reference_path, look_back=25, look_ahead=24)


def hit_metrics(rows, reference_path):
    contact = gv2.first_contact_row(rows, 835, 860)
    metrics = {"contact": contact}
    for after in (20, 30):
        metrics[f"ahead+{after}"], metrics[f"lat+{after}"] = path_ahead(rows, REFERENCE_CONTACT_ROW + after, reference_path)
    metrics["ev850"] = gv2.horizontal_ev(rows[EV_ROW])
    metrics["ev_contact"] = gv2.horizontal_ev(rows[contact]) if contact else float("nan")
    metrics["yaw844"] = gv2.yaw_degrees(rows[PRE_CONTACT_ROW])
    metrics["yaw_contact"] = gv2.yaw_degrees(rows[contact]) if contact else float("nan")
    metrics["pre_ahead844"], metrics["pre_lat844"] = path_ahead(rows, PRE_CONTACT_ROW, reference_path)
    return metrics


def describe(m):
    contact_input = gv2.input_frame_of_row(m["contact"]) if m["contact"] else "-"
    return (f"contact row {m['contact']} (input {contact_input}) | EV@contact {m['ev_contact']:.1f} "
            f"EV@850 {m['ev850']:.1f} | yaw@844 {m['yaw844']:.2f} @contact {m['yaw_contact']:.2f} | ahead@844 {m['pre_ahead844']:+.3f}f "
            f"lat {m['pre_lat844']:+.1f} | ahead+20 {m['ahead+20']:+.3f}f (lat {m['lat+20']:+.1f}) ahead+30 {m['ahead+30']:+.3f}f")


def write_edit_csv(base_ghost, candidate_ghost, path, title):
    """List every input frame where the candidate differs from the base. Returns the number of changed frames."""
    base, candidate = list(bf.decode_rkg(base_ghost)[3]), list(bf.decode_rkg(candidate_ghost)[3])
    lines = [f"# {title}",
             "# input_frame = index in the rkg input stream (0 = first countdown frame); race_frame = input_frame - 240 (0 = timer start)",
             "# face bits: 1=A 2=B 4=item 8=drift; stick -7..7; only changed frames listed",
             "input_frame,race_frame,time_s,orig_face,new_face,orig_stick_x,new_stick_x,orig_stick_y,new_stick_y,orig_trick,new_trick"]
    changed = 0
    for row in range(bf.COUNTDOWN_START_FRAME, min(len(base), len(candidate))):
        if base[row] == candidate[row]:
            continue
        input_frame = row - bf.COUNTDOWN_START_FRAME
        race_frame = input_frame - gv2.INPUT_FRAME_TO_RACE_FRAME
        (old_buttons, old_trick, old_x, old_y), (new_buttons, new_trick, new_x, new_y) = base[row], candidate[row]
        lines.append(f"{input_frame},{race_frame},{race_frame / gv2.FRAMES_PER_SECOND:.3f},{old_buttons},{new_buttons},"
                     f"{round(old_x * 7)},{round(new_x * 7)},{round(old_y * 7)},{round(new_y * 7)},"
                     f"{gv2.TRICK_NAMES.get(old_trick, old_trick)},{gv2.TRICK_NAMES.get(new_trick, new_trick)}")
        changed += 1
    open(path, "w").write("\n".join(lines) + "\n")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=gv2.PENDING_GHOST, help="run the edits are listed against")
    ap.add_argument("--ref-dump", default=gv2.REFERENCE_DUMP, help="CPU replay dump of the reference")
    ap.add_argument("--binary", default=find_host_binary(), help="kinoko_host to replay with")
    ap.add_argument("cands", nargs="+", help="candidate .rkg files")
    a = ap.parse_args()

    reference = gv2.load_dump(a.ref_dump)
    reference_path = gv2.path_of_dump(reference)
    print("27.818 :", describe(hit_metrics(reference, reference_path)))
    for candidate in a.cands:
        stem = os.path.splitext(candidate)[0]
        dump = stem + "_cpu.csv"
        subprocess.run([a.binary, "replay", "--ghost", candidate, "--dump", dump], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        metrics = hit_metrics(gv2.load_dump(dump), reference_path)
        changed = write_edit_csv(a.base, candidate, stem + "_edits.csv",
                                 f"rGV2 L1 fast block hit candidate {os.path.basename(candidate)}; orig = {os.path.basename(a.base)}; {describe(metrics)}")
        print(f"{os.path.basename(candidate)}: {describe(metrics)} | {changed} edited frames")


if __name__ == "__main__":
    main()
