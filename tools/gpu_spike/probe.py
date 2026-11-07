"""GPU port spike (option A): compile real Kinoko engine sources with NVRTC and report what breaks.

Every unannotated function is compiled as device code (-default-device), std headers come from tools/gpu_spike/shim
(thin wrappers over CuPy's bundled libcu++), and each .cc is compiled as its own translation unit (or all together with
--unity). Errors are grouped into categories so the obstacles can be counted.

    python tools/gpu_spike/probe.py source/game/kart/KartMove.cc
    python tools/gpu_spike/probe.py --set kart          # every file of a preset
    python tools/gpu_spike/probe.py --set kart --unity  # one TU, the way a real build would be done
"""

import argparse
import collections
import os
import re
import sys
import time

from cupy_backends.cuda.libs import nvrtc

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CUPY_INC = os.path.join(os.path.dirname(__import__("cupy").__file__), "_core", "include")
CCCL = os.path.join(CUPY_INC, "cupy", "_cccl", "libcudacxx")
SHIM = os.path.join(os.path.dirname(__file__), "shim")
XSRC = os.path.join(os.path.dirname(__file__), "xsrc")  # transform.py output

SETS = {
    "egg": ["source/egg/math/*.cc"],
    "kart": ["source/game/kart/*.cc"],
    "field": ["source/game/field/*.cc"],
    "system": ["source/game/system/*.cc"],
    "rest": ["source/egg/core/*.cc", "source/egg/util/*.cc", "source/abstract/*.cc", "source/abstract/*/*.cc",
             "source/game/field/obj/*.cc", "source/game/field/jugem/*.cc", "source/game/item/*.cc",
             "source/game/render/*.cc", "source/game/scene/*.cc", "source/game/system/map/*.cc"],
}

PRELUDE = '#include <kinoko_gpu_prelude.h>\n'


def options(extra):
    return [
        "--std=c++20", "-default-device", "--fmad=false", f"--gpu-architecture=compute_{os.environ.get('KINOKO_GPU_ARCH', '89')}",
        "--relocatable-device-code=true", "-DREVOLUTION", "-DKINOKO_GPU",
        f"-I{SHIM}", f"-I{CCCL}", f"-I{os.path.join(XSRC, 'include')}", f"-I{os.path.join(XSRC, 'source')}",
        "--diag-suppress=20012,20208,550,177,1444",
    ] + extra


def compile_src(src, name, extra=()):
    prog = nvrtc.createProgram(src, name, [], [])
    t = time.time()
    ok = True
    try:
        nvrtc.compileProgram(prog, options(list(extra)))
    except nvrtc.NVRTCError:
        ok = False
    log = nvrtc.getProgramLog(prog)
    nvrtc.destroyProgram(prog)
    return ok, log, time.time() - t


ERR = re.compile(r'^(?P<file>[^\n(]+)\((?P<line>\d+)\): (?P<kind>error|warning)[^:]*: (?P<msg>.*)$', re.M)

CATEGORIES = [
    ("host-only std (vector/list/string/function/stream)",
     r'namespace "std" has no member "(vector|list|string|function|unordered_map|unique_ptr|print|format|ifstream|ofstream|filesystem|stringstream)'),
    ("std member missing (other)", r'namespace "std" has no member'),
    ("printf/file io/libc", r'identifier "(printf|fprintf|snprintf|fopen|fclose|fread|fwrite|stderr|stdout|exit|abort|strcmp|strlen|strncmp|vsnprintf|va_start|malloc|free)"'),
    ("static/global variable used from device", r'(cannot be directly read in a device function|cannot be directly written in a device function|static variable|__device__ variable)'),
    ("host function called from device", r'calling a __host__ function'),
    ("undefined identifier (other)", r'identifier ".*" is undefined'),
    ("GNU extension / syntax", r'(expected|case range|statement expression)'),
    ("constexpr", r'constexpr'),
]


def categorize(msg):
    for name, pat in CATEGORIES:
        if re.search(pat, msg):
            return name
    return "other"


def expand(patterns):
    import glob
    out = []
    for p in patterns:
        out += sorted(glob.glob(os.path.join(ROOT, p)))
    return [os.path.relpath(f, ROOT).replace("\\", "/") for f in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--unity", action="store_true")
    ap.add_argument("--show", type=int, default=6, help="error lines printed per file")
    ap.add_argument("--log", help="write the full logs here")
    args = ap.parse_args()
    files = list(args.files)
    for s in args.set:
        files += expand(SETS[s])
    units = [("unity.cu", files)] if args.unity else [(f, [f]) for f in files]
    total = collections.Counter()
    fulllog = []
    nok = 0
    for name, members in units:
        src = PRELUDE + "".join(f'#include "{os.path.join(XSRC, m[:-3] + ".cu")}"\n'.replace("\\", "/") for m in members)
        ok, log, dt = compile_src(src, name)
        errs = [m for m in ERR.finditer(log) if m.group("kind") == "error"]
        nok += ok
        cats = collections.Counter(categorize(m.group("msg")) for m in errs)
        total.update(cats)
        print(f"{'OK ' if ok else 'ERR'} {name:60s} {len(errs):4d} errors  {dt:5.1f}s  " +
              ", ".join(f"{k}:{v}" for k, v in cats.most_common()))
        seen = set()
        shown = 0
        for m in errs:
            key = (m.group("msg"))
            if key in seen:
                continue
            seen.add(key)
            if shown < args.show:
                f = os.path.relpath(m.group("file"), XSRC) if os.path.isabs(m.group("file")) else m.group("file")
                print(f"     {f}:{m.group('line')}: {m.group('msg')[:160]}")
                shown += 1
        fulllog.append(f"===== {name}\n{log}")
    print(f"\n{nok}/{len(units)} units compiled.  error categories: " +
          ", ".join(f"{k}:{v}" for k, v in total.most_common()))
    if args.log:
        with open(args.log, "w", encoding="utf-8") as fh:
            fh.write("\n".join(fulllog))


if __name__ == "__main__":
    sys.exit(main())
