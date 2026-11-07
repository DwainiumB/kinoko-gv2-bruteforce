"""Validate the GPU engine on every track / character / vehicle we have a ghost for.

1. Exactness: every ghost is replayed in full on the GPU and on the CPU build (run_gpu.py, one subprocess per ghost so
   a GPU fault can't take the sweep down) and compared bit for bit on all 109 state columns, every frame.
2. Slot size: for one ghost per track, extent_check.py measures the highest private-heap byte any race modifies under
   abusive inputs, and whether any race wrote into the shared template. The GPU tools' default slot (--r-kib) must
   be above the worst track's extent.

    python tools/gpu_spike/validate_all.py                      # all ghosts: the repo's samples/*.rkg + samples/tracks/*/ghosts
    python tools/gpu_spike/validate_all.py --skip-extent
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import run_gpu  # noqa: E402


def ghosts(per_combo=2):
    """All of the repo's samples/*.rkg, plus up to `per_combo` ghosts per (course, character, vehicle) from
    samples/tracks/*/ghosts (hundreds of Luigi Circuit / Funky Kong / Spear ghosts add no coverage)."""
    out = sorted(glob.glob(os.path.join(ROOT, "samples", "*.rkg")))
    seen = {}
    for g in sorted(glob.glob(os.path.join(ROOT, "samples", "tracks", "*", "ghosts", "**", "*.rkg"), recursive=True)):
        try:
            k = run_gpu.combo_of(g)
        except Exception:  # noqa: BLE001 -- reported by main()
            out.append(g)
            continue
        if seen.get(k, 0) < per_combo:
            seen[k] = seen.get(k, 0) + 1
            out.append(g)
    return out


# weight class per character id (0 small, 1 medium, 2 large); a vehicle fits a character when vehicle % 3 == class
CHARACTER_CLASS = [1, 0, 2, 2, 0, 0, 0, 1, 0, 2, 1, 2, 0, 0, 0, 1, 1, 1, 1, 2, 1, 2, 2, 2]


def synthetic(combos, frames, say):
    """Every vehicle (36) once, each with a character of its weight class rotating through all 24 characters, on a
    rotating track, driven by a real ghost's inputs from that track; GPU vs CPU every frame."""
    by_course = {}
    for g, (c, _ch, _v) in combos.items():
        by_course.setdefault(c, g)
    classes = {k: [ch for ch, cl in enumerate(CHARACTER_CLASS) if cl == k] for k in range(3)}
    used = {k: 0 for k in range(3)}
    courses = sorted(by_course)
    bad, chars = 0, set()
    for v in range(36):
        k = v % 3
        ch = classes[k][used[k] % len(classes[k])]
        used[k] += 1
        chars.add(ch)
        c = courses[v % len(courses)]
        rc, out = run(["tools/gpu_spike/run_gpu.py", "--ghost", by_course[c], "--frames", str(frames),
                       "--course", str(c), "--character", str(ch), "--vehicle", str(v)], 1200)
        line = next((l for l in out.splitlines() if "BIT-IDENTICAL" in l or "first mismatch" in l), None)
        ok = rc == 0 and line and "BIT-IDENTICAL" in line
        bad += not ok
        say(f"[{v + 1}/36] {'OK ' if ok else 'BAD'} vehicle {v:2d} character {ch:2d} course {c:2d} "
            f"{COURSE_NAMES_SAFE(c):16s} {line or out[-600:]}")
    say(f"synthetic: {36 - bad}/36 bit-identical; characters covered {len(chars)}/24, vehicles 36/36")


def COURSE_NAMES_SAFE(c):
    return run_gpu.COURSE_NAMES[c] or str(c)


def run(args, timeout):
    p = subprocess.run([sys.executable] + args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return p.returncode, "\n".join(l for l in (p.stdout + p.stderr).splitlines() if "warn" not in l.lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-exact", action="store_true")
    ap.add_argument("--skip-extent", action="store_true")
    ap.add_argument("--synthetic-only", action="store_true",
                    help="only the every-character / every-vehicle runs (ghost inputs replayed with other karts)")
    ap.add_argument("--synthetic-frames", type=int, default=2500)
    ap.add_argument("--extent-r-kib", type=int, default=2048)
    ap.add_argument("--log", default=os.path.join(ROOT, "samples", "data", "gpu_validate_all.log"))
    a = ap.parse_args()
    log = open(a.log, "w", encoding="utf-8")

    def say(msg):
        print(msg, flush=True)
        log.write(msg + "\n")
        log.flush()

    gs = ghosts()
    combos = {}
    for g in gs:
        try:
            combos[g] = run_gpu.combo_of(g)
        except Exception as e:  # noqa: BLE001
            say(f"SKIP (unreadable) {os.path.relpath(g, ROOT)}: {e}")
    t0 = time.time()
    if a.synthetic_only:
        synthetic(combos, a.synthetic_frames, say)
        say(f"total {time.time() - t0:.0f}s")
        return
    if not a.skip_exact:
        say(f"== exactness: {len(combos)} ghosts")
        bad = 0
        for i, (g, (c, ch, v)) in enumerate(combos.items(), 1):
            rc, out = run(["tools/gpu_spike/run_gpu.py", "--ghost", g], 1200)
            line = next((l for l in out.splitlines() if "BIT-IDENTICAL" in l or "first mismatch" in l), None)
            ok = rc == 0 and line and "BIT-IDENTICAL" in line
            bad += not ok
            say(f"[{i}/{len(combos)}] {'OK ' if ok else 'BAD'} course {c:2d} {run_gpu.COURSE_NAMES[c]:16s} char {ch:2d} "
                f"veh {v:2d}  {os.path.relpath(g, ROOT)}  {line or out[-600:]}")
        say(f"exactness: {len(combos) - bad}/{len(combos)} ghosts bit-identical ({time.time() - t0:.0f}s)")

    if not a.skip_extent:
        per_course = {}
        for g, (c, ch, v) in combos.items():
            per_course.setdefault(c, g)
        say(f"== slot extent: {len(per_course)} tracks, R = {a.extent_r_kib} KiB")
        worst = (0, None)
        sizes = {}
        for c, g in sorted(per_course.items()):
            rc, out = run(["tools/gpu_spike/extent_check.py", "--ghost", g, "--r-kib", str(a.extent_r_kib),
                           "--start-frame", "0", "--frames", "0"], 3600)
            m = re.search(r"highest modified byte over all races: (\d+)", out)
            shared = re.search(r"shared template region unchanged: (\w+)", out)
            running = re.search(r"races still running normally \(stage < 4\): (\d+/\d+)", out)
            kib = int(m.group(1)) / 1024 if m else None
            if kib is not None and rc == 0 and shared and shared.group(1) == "True":
                sizes[c] = kib
            if kib is not None and kib > worst[0]:
                worst = (kib, run_gpu.COURSE_NAMES[c])
            say(f"course {c:2d} {run_gpu.COURSE_NAMES[c]:16s} extent {kib if kib is None else round(kib, 1)} KiB, "
                f"shared untouched {shared.group(1) if shared else '?'}, running {running.group(1) if running else '?'}"
                + ("" if rc == 0 and m else f"  ERROR rc={rc}: {out[-600:]}"))
        say(f"worst extent: {worst[0]:.1f} KiB on {worst[1]}")
        if sizes:
            import json, math
            path = os.path.join(HERE, "slot_sizes.json")
            table = json.load(open(path)) if os.path.exists(path) else {}
            for c, kib in sizes.items():  # measured extent + 20%, rounded up to 64 KiB
                table[str(c)] = int(math.ceil(kib * 1.2 / 64) * 64)
            json.dump(dict(sorted(table.items(), key=lambda kv: int(kv[0]))), open(path, "w"), indent=1)
            say(f"wrote {path}: " + ", ".join(f"{c}:{table[str(c)]}" for c in sorted(sizes)))
    say(f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
