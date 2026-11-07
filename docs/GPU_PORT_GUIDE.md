# Porting Kinoko (Mario Kart Wii physics) to the GPU — guide for a Claude instance

Audience: a Claude Code session that has to understand, rebuild, extend or repeat the GPU port of Kinoko.
Everything here was done and verified in the author's Kinoko checkout (tools in `tools/gpu_spike/`, search tools in
`tools/gpu_*.py`). Facts marked **(measured)** were verified bit-for-bit or by benchmark in that repo; anything marked
**(not verified)** is inference. Read `docs/gpu_spike_results.md` and `docs/gpu_work_resume.md` in the repo for the
dated history; this file is the consolidated recipe.

---------------------------------------------------------------------------------------------------------------

## 1. What was achieved

- The **real Kinoko C++ engine** (kart physics, collision, race system, EGG math, ~170 translation units) compiles with
  NVRTC and runs on the GPU, one race per CUDA thread, with no behavioural rewrite of the physics.
- **Bit-exact** against the CPU build on all 109 `FrameState` columns, every frame: 61/61 ghosts on 32 tracks and
  36/36 character/vehicle combinations in `tools/gpu_spike/validate_all.py` (measured). 4,096 relocated clones of a
  race all run to the finish identically (measured).
- Throughput on an RTX 4060 Ti (8 GB): ~2.2-2.6 M race-frames/s with identical inputs, ~1.6 M with divergent inputs;
  a 12-core CPU does ~0.5 M. In real beam/evolutionary searches the achieved rate is ~0.5-1.9 M race-frames/s because
  Python launch overhead and row reads dominate (measured).
- On top of it: `gpu_beam.py` (beam search), `gpu_brute.py` (evolutionary/edit search), `gpu_chain.py`,
  `gpu_window_sweep.py`, marathons. They found a Luigi Circuit run of 68.716 s (below the RTA WR) in 35 s.

## 2. Hard constraints (read before touching anything)

- **Never compile the whole engine as one NVRTC unit.** One file peaks at ~0.9 GB; a single unity compile crashed
  the machine once (~3.7 GB free). `build_gpu.py` compiles one file per subprocess under a memory watchdog and
  links the PTX with the driver linker. Check free RAM first (`python tools/mem.py --min-mb 3500`).
- The PC has 16 GB RAM, often ~3 GB free, and an 8 GB GPU. The browser/WebGL web player can hold several GB of VRAM;
  close it before large searches (otherwise `--work` must shrink and beams get small).
- Toolchain is **pip only**: CuPy, NVRTC (12.9) and the NVIDIA driver (13.1). No CUDA toolkit, no MSVC, no cuBLAS.
  Compile with NVRTC directly, not `cupy.RawModule(code=...)` (it silently appends `-ftz=true`).
- Never rebuild the CPU reference binary while a search is using it; use a separate build directory.
- Windows TDR (~2 s kernel watchdog) is real: do not let one thread do multi-MB work in one kernel (that is why
  Yaz0 decompression happens on the host).

## 3. Architecture decision

Two options were weighed: **A**, compile the existing code for the GPU with a small per-race arena; **B**, rewrite
~6-7k lines of physics as flat C. A was chosen after a time-boxed spike and it worked, so:

> Each race is a private copy of the game's own heap (an EGG ExpHeap) + a private block of statics. Objects are
> constructed on the device by the real init code, so vtables and pointers are valid. A snapshot is a memcpy of that
> slot with pointer relocation. A "search step" is: copy parent slots to child slots, step all children one or many
> frames in one launch, read the state rows.

Why this works (all measured in the spike):
1. Of ~22k engine lines only ~7.9k execute in races (kart 3.4k, collision 1.4k, system 1.3k, math 0.9k).
2. Mutable race state is tiny: at most ~1.5 KB changes; the highest modified heap offset is ~482 KiB of the 64 MiB
   heap. So a slot of 576 KiB (extent + ~20 %) holds a whole race. Only ~1,336 pointers in the first 512 KiB; just 3
   point from shared data into per-race data (ExpHeap block-list links).
3. Math is portable: trig/atan2/frsqrte are the game's own constexpr tables; only `sqrt`/`fabs` come from libm.
   Float32 `* + / sqrt` are bit-identical **only with `--fmad=false`** (27-34 % of multiply-adds differ otherwise).

## 4. The pipeline

```
source/, include/  ──transform.py──▶  tools/gpu_spike/xsrc/   (C++20, per-race statics, device file loader)
xsrc/**/*.cu + runtime.cu ──build_gpu.py (one NVRTC subprocess per file, watchdog)──▶ out/ptx/*.ptx
out/ptx/*.ptx ──driver LinkState──▶ out/kinoko.cubin
run_gpu.py / gpu_engine.py (CuPy RawModule(path=cubin)) ──▶ k_init, k_clone, k_copy_slots, k_step, k_rows
```

Commands (from the repo root):

```
python tools/gpu_spike/transform.py                # regenerate xsrc/ (idempotent, only changed files get new mtimes)
python tools/gpu_spike/build_gpu.py                # incremental by file mtime; --force recompiles everything (~7 min clean)
python tools/gpu_spike/run_gpu.py --ghost <x.rkg>  # one race on GPU vs CPU build, every column, every frame
python tools/gpu_spike/bench_gpu.py --races 2048 [--diverge 0.05]
python tools/gpu_spike/validate_all.py             # exactness on every ghost + slot-size measurement per track
python tools/gpu_spike/extent_check.py             # highest heap byte any race writes under abusive inputs
```

CPU reference binary: `build-gpu-spike/kinoko_host.exe`, configured with `-DKINOKO_HEAP_ALIGN8` so the CPU heap layout
matches the GPU one. `kinoko_host replay --ghost X.rkg --dump out.csv` writes the 109 columns per frame (paths must be
repo-relative; the host exits 1 on a ghost that does not finish but the dump is still written).

## 5. Step by step

### 5.1 First get a trustworthy CPU reference
- Build the host (`kinoko_host`) from the same sources. Replay known ghosts frame-exact (the repo replays 463 RTA
  ghosts and two TAS ghosts on Luigi Circuit; every exit code 0).
- Dump per-frame state: `source/host/FrameState.cc` writes 109 columns (position, quaternions, ext/int velocity,
  speed, drift state, mini-turbo charge, flags, stick, buttons, completion, checkpoint, lap, mushrooms, 12 path
  look-ahead points ×6). These dumps are the ground truth for differential testing.

### 5.2 Source transform (`transform.py`) — what NVRTC needed
NVRTC is C++20 at most and has no GNU extensions. The copy in `xsrc/` gets these mechanical rewrites (counts from the
repo): ~115 `m[r, c]` multi-index subscripts → `m(r, c)` (and `operator[]` declarations → `operator()`); 7 GNU case
ranges expanded; ~46 `static constexpr` locals inside *constexpr functions* lose `static`; 4 flexible array members →
`[1]`; 3 function-scope `static owning_span` with dynamic init → `return {}`; `constexpr Matrix34f() = default` →
non-constexpr; include guards replace `#pragma once` (unity/relative paths reach headers through different spellings);
the EGG ExpHeap minimum alignment/size rounding becomes 8 (GPU loads/stores must be naturally aligned; the CPU build
gets `-DKINOKO_HEAP_ALIGN8` to match). `.cc` files are copied as `.cu` because CMake globs `**/*.cc` repo-wide.

**Trap (cost real debugging time):** only drop `static` from `static constexpr` locals inside *constexpr* functions.
In ordinary functions some code keeps pointers to those tables (e.g. KartMove's turning-param arrays); a non-static copy
lives on the stack and the pointer dangles.

### 5.3 Per-race statics (`statics_rewrite.py`)
The engine uses singletons and 36 mutable statics (`s_instance`, heap lists, caches, `s_proxyList`, …). On the GPU each
race needs its own. The transform renames every use `s_x` → `s_x_ref()`; each class gets `s_x_ref()` (a reference into
the calling race's statics block, `kinoko_race_statics() + idx * KINOKO_STATIC_SLOT`) and `s_x_init()`, and a
generated `kinoko_statics_init.cu` constructs all of them with their original initializers. The set must match what the
CPU `Host::Context` saves (plus the kart proxy list). `kinoko_race_statics()` is computed from
`blockIdx*blockDim+threadIdx`, i.e. thread id = race index within the current layout.

### 5.4 Memory model
- **Template race**: one full game heap (`MEMORY_SPACE_SIZE` = 64 MiB) + statics block, built by `k_init` running the
  real scene-creation path (`SceneManager::changeScene(0)`) on the device.
- **Slot**: `R` private heap bytes followed by the statics block (`STATICS_BYTES = 64 × 128`). `R` per course lives in
  `slot_sizes.json` (measured extent + 20 %; 384–1408 KiB; Mushroom Gorge needs >1 MiB). Too small ⇒ races write into
  the shared template and crash (R ≤ 384 KiB crashed on Luigi Circuit; measured extent 482.2 KiB).
- **Clone** (`k_clone`, template → slots; `k_copy_slots`, slot → slot): word-by-word 8-byte copy; any word that points
  into the source heap range `[src, src+R)` or its statics block is relocated to the destination; anything else
  (course data, parameter tables beyond R) keeps pointing at the shared template. The shared region is never written
  (verified).
- Because relocation is just a scan of aligned 8-byte words, never store non-pointer 64-bit values that look like
  addresses in the copied range, and keep std containers out of the game heap (EGG `operator new` is redirected there).

### 5.5 Device replacements and shims
- `shim/` provides the std headers NVRTC lacks as thin libcu++ wrappers (+ small `std::list`, `std::function`,
  `<compare>`, `snprintf`, `strcmp`, `fprintf` that captures its arguments so `host/FrameState.cc` runs on the device).
  `kinoko_gpu_prelude.h` is force-included in every unit.
- `File_gpu.cu` replaces `abstract/File.cc`: the host uploads the only two files a race opens (`Race/Common.szs` and
  the course `.szs`) and fills `g_kinokoFiles`; `Load()` copies them into the game heap exactly like the CPU version.
- `Decomp_gpu.cu` replaces Yaz0 decompression with the host-decompressed payload (`out/*.szs.expanded`).
- A different course/character/vehicle needs no rebuild: the host uploads that course's archive and `k_init` takes
  course/character/vehicle as arguments.
- Statics with dynamic init + destructors are not allowed in device code; rewrite or shim them.

### 5.6 Build flags (`build_gpu.py:nvrtc_options`)
`--std=c++20 -default-device --relocatable-device-code=true --fmad=false --ftz=true --prec-div=true --prec-sqrt=true
--gpu-architecture=compute_89 -DREVOLUTION -DKINOKO_GPU`, include dirs: `shim`, libcu++ (`cupy/_core/include/.../libcudacxx`),
`xsrc/include`, `xsrc/source`. Change `compute_89` for another GPU. `--ftz=true` matches the CPU build's DAZ mode except
when a result is itself denormal (`denormal_test.py`). Per-thread stack: `cudaLimitStackSize` ≈ 32 KiB (more per
thread would not fit with thousands of threads; the stack reservation is ~1.6 GB at search time and is freed after).

### 5.7 Runtime kernels (`runtime.cu`) and the Python engine (`gpu_engine.py`)
- `k_init(space, size, course, character, vehicle)` — build the template; registers the `RaceConfig` init callback.
- `k_layout(base, stride, staticsOffset)` — point the per-race globals at a contiguous slot range.
- `k_clone`, `k_copy_slots` — snapshot/restore (see 5.4).
- `k_step(inputs, frames, nraces, perRace)` — set the host controller inputs (`buttons, stickX, stickY, trick`) and
  call `SceneManager::calc()` once per frame for `frames` frames; one thread per race.
- `k_rows(out, frame, nraces)` — runs the CPU build's own `Host::WriteStateRow` on the device into a 128-double row:
  `[0]` count, `[1..109]` FrameState columns in header order, `[110..116]` boostCharge, boostMultiplier, front xyz,
  inStunt, inTrick, `[117]` smtCharge (super mini-turbo 0–300, added later), `[120]` stage, `[121]` race timer ms, `[122]` frame.
- `Engine` (Python): `clone_template`, `copy(src_slots, dst_slots)`, `step(first, count, inputs)`, `rows(first, count, frame)`.
  A search keeps *parent* slots, *work* slots (children) and reads rows after each step.

To expose a new state value to searches: add an accessor to the game class if it is private (e.g.
`KartMove::smtCharge()`), write it into an unused `b[...]` slot in `k_rows`, run `python tools/gpu_spike/build_gpu.py`
(only `runtime.cu` recompiles when only its mtime changed), then index that row in the search tool.

### 5.8 Validation discipline (do not skip)
1. `run_gpu.py` per ghost: GPU vs CPU on every column, every frame, **bit-identical**; one subprocess per ghost so a
   GPU fault cannot take the sweep down.
2. `bench_gpu.py`: N clones of one race → all identical; with `--diverge` check clones differ only as inputs differ.
3. `extent_check.py`: abusive inputs (chaos, wall-holding, reversing, trick/item spam) must never write past R or
   into the shared template. Re-run it for a new course; put the result in `slot_sizes.json`.
4. Every search result is replayed on the CPU build before being believed (`gpu_beam` writes a `.rkg` and checks it).
5. Known tiny risk: `EGG::Mathf::asin/acos` call 80-bit `asinl/acosl` on MinGW, double on the GPU; no mismatch was seen.
6. Do not compare raw heap offsets between builds: NVRTC lays out classes with MSVC rules, MinGW with Itanium rules.

## 6. Performance model and tuning
- One race per thread, 32 threads per block. Saturates around ~2,000 races. Cloning 4,096 races ≈ 0.11 s.
- Real searches are launch/Python bound, not engine bound: widening the beam is nearly free until memory runs out
  (beam 128 → 512: 0.20 → 0.97 M race-frames/s on a 60-step run). Slot memory = `(R + statics) × slots`; with R=576 KiB
  and `--work 5800` that is ~3.3 GiB — do not exceed ~90 % of free VRAM (the engine refuses with a clear message).
- Ideas not done: CUDA graphs / fused per-frame kernels, cheaper lookahead, prefiltering children, kernel tuning
  (registers/stack), 64–128 threads per block.

## 7. Building searches on the engine (what exists)
- `tools/gpu_beam.py`: beam search with grafts from reference ghosts (state-aligned), protected lineages, lookahead
  scoring, stop gates (`--stop-completion`, `--gate-pos/dir/lateral`, `--gate-smt-min`, `--gate-mushrooms-min`),
  out-of-bounds guard (`--max-line-dist/--max-line-dy` + `--line-ref-files`), `--wall-invalid`, `--search-ref` windows.
- `tools/gpu_brute.py`: the `brute_force.py` fitness on GPU results (parity-tested 78/78), genome mode and *edit mode*
  (mutates a real input stream: stick runs, button/trick edges, drift ops, grafts, learned operator weights).
- Drivers: `lap1_beam_marathon.py`, `beam_marathon.py` (random settings, elite reuse, CPU-verified reach),
  `gpu_window_sweep.py`, `gpu_chain.py`, `gpu_prune.py`.
- Lessons that cost time: TAS inputs are frame-exact so any upstream change needs downstream re-solving; always audit
  big gains for out-of-bounds (height/distance vs reference line), consumed resources (mushrooms), wall contacts and
  respawns; a search target at a position needs a heading/state condition only if the body heading equals the path
  tangent (not true while drifting).

## 8. File map (all under `tools/gpu_spike/` unless noted)

| File | Role |
|---|---|
| `transform.py`, `statics_rewrite.py` | source → `xsrc/` rewrites, per-race statics |
| `shim/`, `kinoko_gpu_prelude.h` | std-library shims for NVRTC |
| `File_gpu.cu`, `Decomp_gpu.cu` | device file table / host-decompressed Yaz0 |
| `runtime.cu` | device "host system": init, clone, step, state rows |
| `build_gpu.py` | per-file NVRTC under memory watchdog + link to `out/kinoko.cubin` |
| `run_gpu.py` | host-side `GpuRace`: uploads files, launches kernels, compares with CPU |
| `gpu_engine.py` | multi-slot `Engine` used by all searches (`ROW_DOUBLES = 128`) |
| `validate_all.py`, `extent_check.py`, `bench_gpu.py` | exactness, slot-size and speed validation |
| `slot_sizes.json` | per-course slot heap size (KiB) |
| `../gpu_beam.py`, `../gpu_brute.py`, … | searches on the engine |
| `docs/gpu_port_handoff.md`, `docs/gpu_spike_results.md`, `docs/gpu_work_resume.md` | dated history |

## 9. If you have to repeat this for a different simulator
1. Replay-test the CPU build against recorded ground truth first; get a per-frame dump to diff against.
2. Measure *what code runs* (coverage) and *how much state changes* (page-level extent under abusive inputs) before
   choosing between "compile the real thing" and "rewrite".
3. Find every mutable global; make them per-race with a generated init function.
4. Make the allocator's pointers relocatable by confining a race to one contiguous slot and copying with relocation.
5. Compile per file under a memory watchdog; keep FMA off; mirror CPU denormal behaviour.
6. Validate bit-exactly on many scenarios, then measure the slot extent, then optimise.
