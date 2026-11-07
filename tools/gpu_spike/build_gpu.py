"""Build the transformed engine (xsrc) for the GPU: every source file compiled separately to relocatable PTX, then
linked with the CUDA driver's linker into one cubin. Memory-safe by construction:

  - each compile / the link runs in its own subprocess, one at a time;
  - a watchdog kills the subprocess if its working set exceeds --limit-mb or free RAM drops below --floor-mb.
  (A single whole-engine NVRTC compile crashed the PC once; never go back to that.)

    python tools/gpu_spike/transform.py
    python tools/gpu_spike/build_gpu.py                # -> tools/gpu_spike/out/kinoko.cubin

Compiled with NVRTC directly (cupy.RawModule(code=...) appends -ftz=true behind your back). Options: C++20, functions
device by default, no fused multiply-add, flush denormals (matches the CPU build's DAZ, see denormal_test.py).
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
XSRC = os.path.join(HERE, "xsrc")
OUT = os.path.join(HERE, "out")
PTX_DIR = os.path.join(OUT, "ptx")


def cccl_dir():
    import cupy
    return os.path.join(os.path.dirname(cupy.__file__), "_core", "include", "cupy", "_cccl", "libcudacxx")


def units():
    files = []
    for f in sorted(glob.glob(os.path.join(XSRC, "source", "**", "*.cu"), recursive=True)):
        rel = os.path.relpath(f, XSRC).replace("\\", "/")
        if rel.startswith("source/host/") and not rel.endswith(("SceneCreatorDynamic.cu", "FrameState.cu")):
            continue
        files.append(f)
    files.append(os.path.join(XSRC, "kinoko_statics_init.cu"))
    files.append(os.path.join(HERE, "runtime.cu"))
    return files


def gpu_arch():
    """Compute capability to compile for: $KINOKO_GPU_ARCH (e.g. 86, 89), else the first GPU's, else 89."""
    env = os.environ.get("KINOKO_GPU_ARCH")
    if env:
        return env
    try:
        import cupy
        return str(cupy.cuda.Device(0).compute_capability)
    except Exception:
        return "89"


def nvrtc_options(ftz):
    return ["--std=c++20", "-default-device", "--relocatable-device-code=true", "--fmad=false",
            f"--ftz={'true' if ftz else 'false'}", "--prec-div=true", "--prec-sqrt=true",
            f"--gpu-architecture=compute_{gpu_arch()}", "-DREVOLUTION", "-DKINOKO_GPU",
            f"-I{os.path.join(HERE, 'shim')}", f"-I{cccl_dir()}", f"-I{os.path.join(XSRC, 'include')}",
            f"-I{os.path.join(XSRC, 'source')}", "--diag-suppress=20012,20208,550,177,1444,20011,20014"]


# ---------------------------------------------------------------- subprocess side

def compile_unit(src, out, ftz):
    from cupy_backends.cuda.libs import nvrtc
    text = "#include <kinoko_gpu_prelude.h>\n" + f'#include "{src}"\n'.replace("\\", "/")
    prog = nvrtc.createProgram(text, os.path.basename(src), [], [])
    try:
        nvrtc.compileProgram(prog, nvrtc_options(ftz))
    except nvrtc.NVRTCError:
        log = nvrtc.getProgramLog(prog)
        print("\n".join(l for l in log.splitlines() if " error" in l)[:4000])
        return 1
    ptx = nvrtc.getPTX(prog)
    with open(out, "wb") as fh:
        fh.write(ptx if isinstance(ptx, bytes) else ptx.encode())
    return 0


def link(ptx_files, out):
    from cupy.cuda import function
    state = function.LinkState()
    for p in ptx_files:
        with open(p, "rb") as fh:
            state.add_ptr_data(fh.read(), os.path.basename(p))
    cubin = state.complete()
    with open(out, "wb") as fh:
        fh.write(cubin)
    return 0


# ---------------------------------------------------------------- watchdog

class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def proc_mb(pid):
    h = ctypes.windll.kernel32.OpenProcess(0x0410, False, pid)  # QUERY_INFORMATION | VM_READ
    if not h:
        return 0
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    ctypes.windll.kernel32.CloseHandle(h)
    return max(pmc.WorkingSetSize, pmc.PagefileUsage) / 2**20 if ok else 0


def free_mb():
    sys.path.insert(0, os.path.join(HERE, ".."))
    from mem import free_mb as f
    return f()[0]


def guarded(args, limit_mb, floor_mb, label):
    """Run `python build_gpu.py <args>` with the watchdog; return (rc, peak MB, output)."""
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__)] + args, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    peak = 0
    while p.poll() is None:
        mb = proc_mb(p.pid)
        peak = max(peak, mb)
        free = free_mb()
        if mb > limit_mb or free < floor_mb:
            p.kill()
            p.wait()
            out = p.stdout.read()
            print(f"KILLED {label}: process {mb:.0f} MB (limit {limit_mb}), free RAM {free} MB (floor {floor_mb})")
            return -9, peak, out
        time.sleep(0.1)
    out = p.stdout.read()
    return p.returncode, peak, "\n".join(l for l in out.splitlines() if "UserWarning" not in l and "warnings.warn" not in l)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    ap.add_argument("--link", nargs="*", help=argparse.SUPPRESS)
    ap.add_argument("--no-ftz", action="store_true")
    ap.add_argument("--limit-mb", type=int, default=1500)
    ap.add_argument("--floor-mb", type=int, default=1500)
    ap.add_argument("--force", action="store_true", help="recompile every unit")
    a = ap.parse_args()
    if a.unit:
        return compile_unit(a.unit, a.out, not a.no_ftz)
    if a.link is not None:
        return link(a.link, a.out)

    os.makedirs(PTX_DIR, exist_ok=True)
    us = units()
    shim_mtime = max(os.path.getmtime(f) for f in glob.glob(os.path.join(HERE, "shim", "*")))
    ptxs, peaks, failed = [], [], []
    t0 = time.time()
    for i, u in enumerate(us):
        rel = os.path.relpath(u, HERE).replace("\\", "/")
        out = os.path.join(PTX_DIR, rel.replace("/", "__") + ".ptx")
        ptxs.append(out)
        if not a.force and os.path.exists(out) and os.path.getmtime(out) > max(os.path.getmtime(u), shim_mtime):
            continue
        args = ["--unit", u, "--out", out] + (["--no-ftz"] if a.no_ftz else [])
        rc, peak, text = guarded(args, a.limit_mb, a.floor_mb, rel)
        peaks.append((peak, rel))
        if rc != 0:
            failed.append(rel)
            print(f"FAIL {rel}\n{text}")
            if rc == -9:
                return 2
        if i % 20 == 0:
            print(f"  [{i + 1}/{len(us)}] {time.time() - t0:.0f}s  free {free_mb()} MB", flush=True)
    if peaks:
        peaks.sort(reverse=True)
        print("compile peak memory (top 3): " + ", ".join(f"{p:.0f} MB {r}" for p, r in peaks[:3]))
    if failed:
        print(f"{len(failed)} units failed")
        return 1
    cubin = os.path.join(OUT, "kinoko.cubin")
    rc, peak, text = guarded(["--link", *ptxs, "--out", cubin], a.limit_mb * 2, a.floor_mb, "link")
    print(f"link rc={rc} peak {peak:.0f} MB in {time.time() - t0:.0f}s total")
    if rc != 0:
        print(text[-4000:])
        return 1
    print(f"-> {cubin} ({os.path.getsize(cubin) / 2**20:.1f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
