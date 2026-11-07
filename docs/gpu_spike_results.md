# GPU port spike (option A): results

Follow-up to `gpu_port_handoff.md`. Option A (compile the real engine for the GPU) **works**: the whole engine runs on
the GPU, initialises a race on the device, and reproduces CPU Kinoko bit for bit. Decision: continue with A.

## Results (2026-10-02, RTX 4060 Ti)
- **Exactness:** full races of `samples/tracks/luigi-circuit/ghosts/tas/1142.rkg`, `samples/tracks/luigi-circuit/ghosts/tas/702.rkg`, the RTA WR ghost (Kasey 1:08.733) and
  `samples/tracks/luigi-circuit/runs/best/lc-spear-68916.rkg` are bit-identical to the CPU on all 109 FrameState columns, every frame.
- **Many races:** one race is cloned into N slots (1 MiB private heap + 8 KiB statics each, pointers relocated during
  the copy, course data shared). 4,096 clones run to the finish, all bit-identical; the shared region is never written.
- **Throughput** (unoptimised, one race per thread, 32 threads per block):

  | races | same inputs | 5 % random inputs per frame |
  |------:|------------:|----------------------------:|
  | 1     | ~4.5 k frames/s (221 us/frame) | |
  | 1,024 | 2.25 M race-frames/s | |
  | 2,048 | 2.65 M | 1.62 M |
  | 4,096 | 2.61 M | |

  CPU reference: about 40 k frames/s per core, so roughly 0.5 M for 12 cores, before Python pipe overhead. The GPU is
  about 3-5x the whole CPU today. Saturation starts around 2,000 races. Cloning 4,096 races takes 0.11 s
  (about 27 us per snapshot restore).

## How to run (all in `tools/gpu_spike`)
```
python tools/gpu_spike/transform.py      # source/include -> xsrc/ (C++20, per-race statics, GPU file/decomp)
python tools/gpu_spike/build_gpu.py      # per-file NVRTC -> PTX, driver link -> out/kinoko.cubin (~7 min clean)
python tools/gpu_spike/run_gpu.py --ghost samples/tracks/luigi-circuit/ghosts/tas/1142.rkg      # one race vs CPU, all columns
python tools/gpu_spike/bench_gpu.py --races 2048 [--diverge 0.05]   # clones, exactness, throughput
```
CPU reference binary: `build-gpu-spike/kinoko_host.exe`, configured with `-DKINOKO_HEAP_ALIGN8` (same heap layout).

## What it took
- `transform.py`: NVRTC is C++20 only and has no GNU extensions, so the copy gets these rewrites:
  - 115 `m[r, c]` subscripts become `m(r, c)`
  - 7 case ranges are expanded
  - 46 `static constexpr` locals inside constexpr functions lose the `static` (**only** in constexpr functions:
    elsewhere code keeps pointers to these tables)
  - 4 flexible arrays become `[1]`
  - include guards are added
  - the heap's minimum alignment becomes 8
  - the 36 mutable statics become per-race `s_x_ref()` accessors (`statics_rewrite.py`)
- `.cc` files are copied as `.cu`, because CMakeLists globs `**/*.cc` over the whole repo.
- `shim/`: libcu++ wrappers, plus a small `std::list`, `std::function`, `<compare>`, `snprintf` and string functions.
  `fprintf` captures its arguments, so `run_gpu.py` can run `host/FrameState.cc` on the device.
- `File_gpu.cu` / `Decomp_gpu.cu`: files are uploaded by the host and Yaz0 is decompressed on the host. One GPU thread
  decompressing several MB could exceed the Windows watchdog (TDR, about 2 s).
- `runtime.cu`: kernels `k_init`, `k_layout`, `k_clone` (relocating copy), `k_step`, `k_state`, `k_row`.

## Gotchas learned
- **Never compile the whole engine as one NVRTC unit**: it crashed the PC. One file needs about 0.9 GB, so
  `build_gpu.py` compiles one file at a time in a subprocess with a memory watchdog, then links.
- `cupy.RawModule(code=...)` silently appends `-ftz=true`; compile with NVRTC directly.
- `--ftz=true` matches the CPU's DAZ mode, except that denormal *results* are flushed (`denormal_test.py`).
- NVRTC on Windows lays classes out with MSVC rules, not MinGW's Itanium rules, so raw heap offsets differ between
  builds. Compare by value (`run_gpu.py`), not by heap diff.
- `EGG::Mathf::asin/acos` call `asinl/acosl` (80-bit x87 on MinGW); the GPU uses double. No mismatch was seen on any
  ghost, but it is a possible source of rare 1-ulp differences.
- Statics with dynamic initialisation and destructors are not allowed in device code (see the shims).

## Next steps
1. Speed: profile register and stack use. Try 64-128 threads per block, and run many frames per launch (the beam
   search's 30-frame lookahead fits in one launch).
2. Search integration: a Python driver that keeps the beam on the GPU (snapshot = `k_clone` slot to slot; give
   `k_clone` a source-slot index) and steps all children plus their lookaheads in one launch. Policy evaluation
   either on the GPU (small MLP) or batched on the CPU.
3. Shrink R from 1 MiB towards about 512 KiB after re-measuring the dirty extent with the GPU layout.
4. Fold the transform's rewrites into the real source (they compile on MinGW too), so the GPU build no longer needs
   the copy.

## Slot size and beam width (2026-10-02, follow-up)
- `extent_check.py`: highest byte a race ever modifies, in the GPU layout, over 192 abusive races (random chaos, holding into
  walls both ways, reversing, trick/item spam, drifting in circles): **482.2 KiB**, identical to the CPU build's 482.2 KiB.
  Shared region never written. R = 512 KiB is exact but only a 6 % margin; **R = 576 KiB** is the default now (20 % margin).
  R <= 384 KiB crashes (illegal memory access). R = 576 KiB: 1,024 clones bit-identical on 3 ghosts, 2.2-2.3 M race-frames/s.
- The search is bound by per-frame launch/Python overhead, not by the engine: doubling the batch doubled the work done in
  the same time (beam 128 -> 256: 204 k -> 417 k race-frames/s on a 60-step run; 384: 899 k; 512: 968 k).
- Full search from the 68.872 s pool: CPU beam ~19 / 192 s -> 68.871 s; GPU beam 128 / 38 s -> 68.869 s; GPU beam 512 /
  77 s -> 68.864 s (peak GPU memory 7,753 of 8,188 MiB, too tight to be the default; default is now beam 384, work 5800).
