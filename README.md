# rGV2 Ultra block-hit brute force (Kinoko GPU search)

> **Not the official Kinoko.** This repo is an unofficial copy of [Kinoko](https://github.com/vabold/Kinoko) by vabold and its
> contributors (MIT), plus a web-player fork and the search tools described below. For Kinoko itself, use the upstream repo.
> Kinoko's own README (building, extracting the game files) is kept at [docs/KINOKO_README.md](docs/KINOKO_README.md).

These are the tools used to re-find the "fast block hit" on SNES Ghost Valley 2 (Ultra shortcut, 3 laps,
Funky Kong + Standard Bike L). Every run is replayed in Kinoko, the CPU engine on this branch or a bit-identical GPU
build of the same code. Each search tool also writes its candidates as `.rkg` ghosts.

**Status (2026-11-07):** this is work-in-progress research code, not a finished tool.
- **Found:** a lap 1 that crosses the line **~1.28 frames earlier than the 27.818** (L1 ≈ 9.397 vs 9.418), CPU-verified.
- **Not found:** the second bounce into the ultra shortcut at the start of lap 2. It looks as precise as the block hit itself.
  So there is **no 3-lap time yet**.
- **Not checked:** nothing has been checked in Dolphin yet. The block hit is precise to ~0.02 units, so an emulator check matters.
- **Details:** what worked, what didn't, and every candidate are in `samples/tracks/ghost-valley-2/SEARCH_RESULT.md`.
  The background (sam's method, the thread's lessons) is in `samples/tracks/ghost-valley-2/ANALYSIS.md`.

## What's here

| Path | What it is |
|---|---|
| `source/host/KSearchSystem.*` | `kinoko_host search`: step / save / restore / state over stdin+stdout, the CPU reference for the GPU engine |
| `source/host/KBruteSystem.*`, `KDriveSystem.*` | `kinoko_host brute` (evaluate a whole input list) and `drive` (per-frame closed loop) |
| `source/host/FrameState.cc`, `KReplaySystem.cc` | `kinoko_host replay --ghost X.rkg --dump X.csv`: one CSV row per frame (position, rotation, EV, completion, per-tire contact, ...) |
| `tools/gpu_spike/` | the GPU port: copies Kinoko into `xsrc/` with C++20 rewrites, compiles it with NVRTC, and runs thousands of races in parallel |
| `tools/gv2_common.py` | **start here**: the terms the tools use (row, input frame, progress on the reference path), paths, and the shared code (GPU helpers, population search loop, path maths) |
| `tools/brute_force.py`, `tools/kinoko_search.py` | .rkg encode/decode, and the wrapper for `kinoko_host search` |
| `tools/evolve.py` | the earlier Yoshi Falls population search the gv2 searches were built from (kept for reference, not used by them) |
| `tools/gv2_hit_evolve.py` | **the block-hit search**: edits stick inputs in a window before contact, scored on progress after the hit |
| `tools/gv2_tail_evolve.py` | the follow-up search: fits the superhops after the hit, or chases the lap 2 entry |
| `tools/gv2_verify.py`, `gv2_laps.py`, `gv2_metrics.py`, `gv2_hitcmp.py`, `gv2_splice.py`, `gv2_gpu_parity.py` | CPU replay checks, lap-line crossing times, yaw/EV/progress metrics, splicing, GPU vs CPU parity |
| `tools/gv2_examples/*.sh` | real command lines used for the runs in SEARCH_RESULT.md, and `regression_check.sh`: short fixed-seed runs of every tool to prove a code change didn't change results |
| `samples/tracks/ghost-valley-2/ghosts/` | the community ghosts: the 27.818, the 28.165, slimpanda's PENDING lap 1, sircorvid's 20.444, sam's two lap 1 candidates |
| `samples/tracks/ghost-valley-2/results/` | our candidates (`.rkg`) with input-edit CSVs in sam's format (input frame, race frame, orig vs new) |
| `docs/GPU_PORT_GUIDE.md`, `docs/gpu_spike_results.md` | how the GPU port works and how it was verified |

## Requirements

- **Game files:** your own Mario Kart Wii `Race/` folder next to the repo root (`Race/Common.szs`, `Race/Course/*.szs`), as in Kinoko's README.
  Nothing from the game is in this branch.
- **Native build:** a native (non-Emscripten) build of `kinoko_host`. The tools find it at `build-host-release/`, `build-host/` or `build/`,
  or you can set `KINOKO_HOST=path/to/kinoko_host`.
- **For the GPU search:**
  - an NVIDIA GPU, plus Python 3.11 with `numpy` and CuPy (`pip install cupy-cuda12x`), which brings the NVRTC compiler;
  - the target architecture is your first GPU's compute capability; set `KINOKO_GPU_ARCH=86` (etc.) to override it.
  - Tested on Windows with an RTX 40-series card: about 1.6M race-frames/s with different inputs per race, against about 0.5M on a 12-core CPU.

## Setup

```bash
# 1. native build (any C++23 compiler; on Windows we used mingw-w64 + ninja)
cmake -B build-host-release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-host-release --target kinoko_host

# 2. GPU engine: copy the engine into xsrc/ with the C++20 rewrites, then compile to tools/gpu_spike/out/kinoko.cubin
python tools/gpu_spike/transform.py
python tools/gpu_spike/build_gpu.py
```

**Warning about step 2:** compiling the whole engine as a single unit with ptxas `-v` once crashed the author's PC, which had
about 3.7 GB of RAM free. `build_gpu.py` now compiles file by file under a memory watchdog (~0.9 GB per file) and links at the end.
Run it with a few GB free and nothing heavy open. Check with `python tools/mem.py` first.

## Reproduce the lap 1 hit

```bash
# reference dump of the 27.818 (the GV2 tools read it)
mkdir -p runs/gv2
build-host-release/kinoko_host replay --ghost samples/tracks/ghost-valley-2/ghosts/rGV2_27.818_slimpanda_best.rkg --dump runs/gv2/gv2_27818.csv

# the GPU must match the CPU on this track before you trust any search (expect 0 mismatches over 2080 frames)
python tools/gv2_gpu_parity.py samples/tracks/ghost-valley-2/ghosts/rGV2_27.818_slimpanda_best.rkg runs/gv2/gv2_27818.csv

# block-hit search on slimpanda's PENDING lap 1 (defaults = the settings that found hits A/D/E/F, ~5-25 min)
python tools/gv2_hit_evolve.py --out runs/gv2/evoA --gens 150

# CPU-verify the candidates: contact row, EV, yaw, progress vs the 27.818 at +20 f
python tools/gv2_verify.py runs/gv2/evoA_0.rkg runs/gv2/evoA_1.rkg
```

The example scripts in `tools/gv2_examples/` start from earlier outputs under `runs/gv2/`. To rerun them, copy those outputs in first:
`cp samples/tracks/ghost-valley-2/results/* runs/gv2/`. Some intermediate seeds (`runs/gv2/_l2*`, `l2st*`) are not included, so
the lap 2 scripts show the flags used rather than reproduce exactly.

**Rows vs frames:** rkg input frame = dump row − 172, and sam's "race frame" = input frame − 240. (The dump's own `raceFrame` column is row − 171, one more.) The 27.818's L1 contact is row 846 = input frame 674 = race frame 434. `tools/gv2_common.py` explains all the terms the tools use.

## What the search does (and what we learned)

`gv2_hit_evolve.py` is a (μ+λ) population search on the GPU, built along the lines the thread worked out with sam:
- **Edits:** stick only, mostly vertical (`--p-y 0.8`), within a small budget (`--budget 10`). It edits from `--from-row`, and inputs from `--freeze-from` on are kept.
- **Contact:** the hit must happen within `--contact-lo..hi`.
- **Score:**
  - progress along the 27.818's path 20 and 30 frames after contact (`--fwd-after`);
  - plus capped EV and a bonus for right yaw ("right" = higher, less negative yaw);
  - minus a **pace penalty** for being ahead of or behind the reference before contact (`--w-pace`). Without it, hits pull ahead and break the superhops;
  - minus a lateral penalty for drifting off the reference path before contact.

What we learned is in SEARCH_RESULT.md:
- The hit is reachable in only 3–7 stick edits.
- Score after the hit decides the superhops more than score at the hit: hit A scored lower than E but gave the better lap 1.
- sircorvid's earlier approach gets a +3.2 f hit that does not carry to the line.
- The lap 2 entry (second bounce at ~row 1026, then the shortcut) is the open problem.

## Licence

This branch is MIT, the same as Kinoko. The search code was written with Claude (Anthropic).
