# rGV2 L1 fast block hit search on the PENDING ghost (2026-11-04)

> On the `gv2-bruteforce` branch, the main candidates named `runs/gv2/<name>.rkg` (and their `_edits.csv`) are in `results/`, and community ghosts are in `ghosts/`. Logs and intermediate runs are not included. Setup and usage: the repo `README.md`.

Base: `ghosts/rGV2_22.000_slimpanda_L1_with_L3_movement_PENDING.rkg`. Reference: `ghosts/rGV2_27.818_slimpanda_best.rkg`.
Tools: `tools/gv2_hit_evolve.py` (GPU search), `tools/gv2_verify.py` (CPU replay + sam-format edit CSV), `tools/gv2_hitcmp.py`.
Everything below is **CPU-verified** with `build-host-release/kinoko_host.exe replay --dump`, and matches the GPU scores exactly.

## Result: the hit is found, one frame earlier and +0.8 to +0.9 f ahead

| candidate | edits | contact row | EV at contact / row 850 | yaw at 844 / at contact | ahead at +20 / +30 | lateral at +20 | L1 line (tail inputs unchanged) |
|---|---|---|---|---|---|---|---|
| 27.818 (ref) | - | 846 | 62.5 / 44.3 | -112.60 / -118.07 | 0 / 0 | 0 | row 976 (~975.51) |
| PENDING (base) | 0 | 845 | 34.4 / 16.3 | -111.64 / -117.99 | -6.6 f (fails) | +484 | never finishes the lap |
| sam 300 (on the 27.818) | ~105 | 846 | 62.7 / 48.1 | -112.60 / -116.52 | +0.43 / +0.37 | +145 | - |
| **E** `runs/gv2/gv2_L1hit_E.rkg` | 4 | **845** | 60.9 / 53.7 | -111.65 / -114.68 | **+0.814 / +0.809 f** | **+17** | **row 977 (~976.59)** |
| **F** `runs/gv2/gv2_L1hit_F.rkg` | 3 | 845 | 61.0 / 53.4 | -111.64 / -114.67 | +0.830 / +0.826 f | +15 | row 1001 |
| **D** `runs/gv2/gv2_L1hit_D.rkg` | 7 | 845 | 63.7 / 49.1 | -110.58 / -113.42 | **+0.892 / +0.875 f** | +110 | doesn't finish |
| A `runs/gv2/gv2_L1hit_A.rkg` | 3 | 845 | 61.6 / 56.1 | -111.64 / -114.67 | +0.842 / +0.846 f | -68 | row 998 |

"ahead" = along-track position on the 27.818's own path at the same dump row, minus the row, in frames.
Lateral = signed offset from that path in units. Contact = first row with flags bit 0x400 (1024) in 835-860.
Each candidate's input edits vs the PENDING ghost, in sam's CSV format: `runs/gv2/gv2_L1hit_<X>_edits.csv`.
Every edit falls in input frames 603-674 (race frames 363-434), all stick, no buttons or d-pad.
- E: 603 X -1→-3, 631 Y 6→7, 646 Y 2→4, 656 Y 2→0
- F: 653 Y -4→-6, 654 Y -1→0, 674 X 7→6
- D: 606 Y 7→5, 626 Y -1→0, 653 Y -4→-6, 659 Y -7→-6, 660 Y 7→6, 666 Y 7→4, 673 X 7→6

**Recommended: E.** It is on the 27.818's line 20 f after the hit (17 u), and it crosses the L1 line only ~1.1 f behind the 27.818 with the
post-hit inputs left as they are. But by the line it is 438 u off the 27.818's line, with EV 7.6 against 41.9 (row 976), so it does NOT yet
enter lap 2 in a usable state. It is +0.00065 completion ahead (≈ +0.8 f) until row ~962, and loses that over rows 965-977, where the
27.818 is back up to 86.5 speed and E stays at 80.8. That is the superhop sequence still needing a fit.
F and D hit harder or further forward, but end up 15-110 u off the line, and their unchanged tails lose 20+ rows.

## Facts settled on the way
- GPU parity on the PENDING ghost: 1049 frames, 0 mismatches (`tools/gv2_gpu_parity.py ... runs/gv2/gv2_22000.csv`).
- **Yaw sign:** yaw = atan2(2(qx·qz+qw·qy), 1-2(qx²+qy²)) in degrees (as in `tools/gv2_metrics.py`).
  "Right" = **higher (less negative)**. The L2 table values (-113.2 beats -114.4) match the 27.818's yaw ~2 f before
  the L2 contact (row 1396: -112.9; contact row 1398). sam's better L1 candidates also arrive with higher yaw (-116.5 / -117.6
  against -118.1). All good candidates here have +1 to +3.5° vs the 27.818 at contact.
  (Physically, holding stick X +1 makes this yaw go down. So "right yaw" in the community's sense means the kart has turned
  less far at contact. Treat the label as a convention, not a direction on screen.)
- No drift is active in the run-up (driftState 0 on rows 765-849 on both ghosts; the kart is airborne off the ramp at row 784), so a
  drift-validity gate does not apply.
- Frame conventions: dump row = engine frame; rkg input frame = row - 172 (`COUNTDOWN_START_FRAME`). The dumps' `raceFrame`
  column = row - 171. The input frames in the CSVs use -172, so the 27.818's contact (row 846) = input 674 = race frame 434.
- The pending ghost holds face buttons 3 (A+B) on rows 789-846, where the 27.818 holds 11 (A+B+bit 8).

## What worked
- sam's setup: small edit budget (penalty above 6-12 edits), 80-90 % of mutations on stick Y, edits only in rows 771-846 (or 740-846),
  everything from row 847 on (B release / hit) frozen to the base.
- Score: ahead at contact+20/+30 (w 100) + EV@850 capped at 50 (w 3) + yaw vs ref at row 844 (w 5) + pace penalty |ahead| > 0.25 f
  before contact (never active: the pending ghost is already +0.13 f, 11 u to the side, before the hit).
- Population 2048 runs at ~0.4 s/generation on the 4060 Ti (~2.4 GB VRAM). Every search converged within 50-100 generations,
  i.e. under 1 minute. No rebuild was needed.
- Run F/G: an extra post-contact lateral penalty (`--w-postlat 1 --postlat-tol 30`), seeded with A, D and E, gives
  F (on the line, 3 edits).

## What didn't
- `--btn-from` the 27.818 (run B, face 11 instead of 3 in the window): raises the base EV to 32.9, but it needs 60 changed frames and the best was only +0.53 f.
- Seed 2 (run C) stuck in a local optimum at -0.48 f. The search is very multimodal, so run several seeds.
- Scoring at +20 alone does not predict the lap: A/D/F score higher than E there but lose 20+ rows afterwards with the unchanged tail.

## Logs
`runs/gv2/evoA.log`, `evoBatch1.log` (B-E), `evoBatch2.log` (F-G). Each candidate has `_cpu.csv` (dump) and `_edits.csv`.
Commands: `python tools/gv2_hit_evolve.py --pop 2048 --gens 200 --out runs/gv2/evoX [--seed-rng N] [--budget N] [--p-y P]
[--from-row 740] [--w-postlat 1 --seed ...]`, then `python tools/gv2_verify.py runs/gv2/evoX_0.rkg`.

## Superhop fitting after the hit (same day, second pass)

Tools: `tools/gv2_tail_evolve.py` (GPU; genome = stick X/Y + face buttons + trick per row, hop-timing shift mutations),
`tools/gv2_splice.py` (candidate up to row S, then the 27.818's inputs shifted by d), `tools/gv2_laps.py` (sub-frame lap-line
crossings from completion, CPU dumps).

**Result: L1 line 1.08 f earlier than the 27.818** -- `runs/gv2/gv2_L1_E_superhops_T1.rkg` (CPU-verified: line at row 974.43 vs
975.51, i.e. L1 ≈ 9.400 vs 9.418). It is E's hit + 17 edits in rows 849-1000 (hop timing and sticks), then the 27.818's inputs shifted
one frame earlier. At the line it is on the 27.818's line (lateral 38 u), EV 45.4 (ref 41.9), speed 80.8 (same).
Edits vs E: `runs/gv2/gv2_L1_E_superhops_T1_edits.csv` (rows after 1000 in that file are the shifted 27.818 tail).

| step | L1 line vs 27.818 | lateral at the line | lap-2 entry |
|---|---|---|---|
| E, PENDING tail unchanged | +1.08 f | +438 u | EV 7.6, unusable |
| E + 27.818 tail spliced (S=969, d=+1) | +0.12 f | +379 u | unusable |
| **T1** (fit rows 849-1000, score line + lateral at 976-1030) | **-1.08 f** | +38 u | no hop at ~1003, 2nd bounce fails |
| **A + fit** `runs/gv2/gv2_L1_A_superhops.rkg` (rows 849-1000, same settings as T1, seeded with T1's hops grafted onto A) | **-1.28 f** (line 974.23) | -17 u (-20 at row 1000) | EV 46.4 at 976; lap 2 not tried yet |
| F + fit `runs/gv2/gv2_L1_F_superhops.rkg` | -0.64 f | +310 u | off the line |
| D + fit `runs/gv2/tailD_0.rkg` | +21.5 f | | fails: D leaves the hit 110 u off, T1's hops don't carry over |
| T2 (fit to 1040, + sync to the 27.818 one frame ahead, + EV after the 2nd bounce) | -1.06 f | +76 u | 2nd bounce happens (EV 43), within 25 u at row 1024, desyncs after |
| T3 (fit to 1110, + completion at row 1300) | -1.06 f | | stuck: no candidate gets the ultra shortcut |

**What the lap-2 entry actually is:** after the line the 27.818 drifts (flags 23, rows ~980-1000), hops at ~1003 (airborne to
~1024), bounces off the block again at ~1026 (speed 83 → 7, EV → 51) and then creeps with high EV, going backwards in
completion (2.028 → 2.000 by row 1200), until completion jumps to 2.92 by row ~1300. That is the ultra shortcut, and it takes most of lap 2.
T2 gets within 25 u of that state at row 1024 but leaves the bounce at EV 44.7 against 47.6 and is 800 u off by row 1080. Splicing the
27.818's inputs (S = 940-1010, d = 0..+2) onto T1 never gets the shortcut (best completion 2.19 at row 1300 vs 2.92).
So **the bounce at ~1026 → shortcut sequence is as precise as the fast block hit**. Nothing gets lap 2 yet, so no 3-lap time yet.

**Best L1 so far: A + fit, 0.20 f better than T1** (CPU-verified, L1 ≈ 9.397 vs 9.418). A's hit scored lower than E's at +20 (+0.842 f, 68 u off) but its line suits the superhops better. Run: `runs/gv2/tail_DFA.sh`, log `runs/gv2/tail_DFA.log` (each fit converged in ~2.5 min). Edits vs PENDING: `runs/gv2/gv2_L1_A_superhops_edits.csv`.

## What's left
1. **Lap-2 entry / ultra shortcut** (rows ~1000-1300): needs its own hit-style search. Freeze T1 up to row ~990, evolve rows ~990-1100
   with a small edit budget, and score completion at row ~1300 (did the shortcut happen) plus sync to the 27.818 one frame ahead from ~1300
   on, so the 27.818's L2 inputs (shifted) can carry through to the L2 block hit at ~1398. The per-generation cost is ~1.3 s at pop 2048 to row 1320.
   An alternative is to give up part of the 1.08 f: sync exactly to the 27.818 (tail-shift 0) before the 2nd bounce and keep only
   what's left of the gain.
2. Then splice the 27.818's L2/L3 back in after the shortcut, or re-search them. This needs the state to match closely enough for the L2 hit.
3. **Lap 2**: the same search around the L2 contact (row ~1398, input ~1226). L3 is already ~1 f early on slimpanda's run.
4. **Dolphin check**: the candidate .rkg files are written by `bf.encode_rkg` with finish time 0 and a generic header. Re-encode
   with the real time and header (or splice the inputs into slimpanda's file) before checking on console/Dolphin.
   The block hit's precision (~0.02 u) is exactly where an emulator difference would show up.

## Lap 2 entry for A (third pass, 2026-11-04): not found yet

Goal: carry `runs/gv2/gv2_L1_A_superhops.rkg` (L1 line 1.28 f ahead) through the 2nd block bounce and the ultra shortcut
(completion ≥ 2.9 by row ~1300). **No run got the shortcut.** Best completion at row 1300 in every search: ~1.92 (27.818: 2.92).

**How the shortcut actually works** (from the 27.818 dump):
1. Row ~1026: the block bounce launches the kart backwards (EV 49-53 for ~40 frames, speed ~8).
2. Row ~1100: it comes to a dead stop at about (x -29151, z -10333).
3. Rows 1100-1154: it turns round and drives the course backwards, drifting at rows 1132-1144 and firing a mini-turbo
   (speed 80 → 102 → 120 by row 1154).
4. Row ~1158: it takes a ramp off the side of the track near x ≈ -26900 and is airborne through ~1200 (up to 400 u higher),
   about 2000 u to the side of the lap line. It never enters checkpoint 34 (the one just behind the line), so the game keeps
   it on checkpoint 0 / completion 2.000, and when it lands in checkpoint 33's zone (row 1202) completion jumps to 2.97.
Every candidate that misses the ramp drives through checkpoint 34 on the ground at ~row 1162-1166. That counts as driving back
over the line: completion drops below 2.0 and stays a full lap short (1.92 at row 1300).

| stage (log in `runs/gv2/`) | rows searched | result |
|---|---|---|
| splice A + 27.818 inputs (`spliceAL2.log`) | - | A arrives at row 1000 at 72.6 speed (ref 80.8) without the drift/hop; bounce EV 9; stops 1700 u short; comp 2.10 |
| l2entry (`l2entry.log`, shift 1, 25 min) | 976-1110 | bounce 22 u off at row 1030, EV 42; stop 490 u off; on the path again by 1280-1300 (16-28 u) but misses the ramp: comp 1.92 |
| l2entry2 (extended to 1200) | 976-1200 | stuck on its seed for 600 gens (stopped) |
| stage 1 (`l2stage1.log`, 10 min each) | 976-1040, scored to the stop at 1110 | shift 1: stop 329 u off; **shift 0: stop 284 u off**; bounce EV 40-45 vs 49-53, hitting the block 20-40 u higher |
| stage 2 (`l2stage2.log`) | 1095-1200 from stage 1 shift 0 | path sync 2364 → 444 u, but no mini-turbo (68-71 speed vs 80-120): misses the ramp |
| stage 2b (`l2stage2b.log`, + speed target at row 1154) | 1095-1200 | gets the boost (120 speed at 1150-1158) but passes ~500-580 u left of the ramp: checkpoint 34 at row 1162 |
| stage 2c (`l2stage2c.log`, + lateral penalty at 1140-1162) | 1095-1200 | trades the boost away for line-up and still 135 u off at the ramp; comp 1.92 |

Closest candidates (CPU-verified dumps next to each file): `runs/gv2/l2st1_0_0.rkg` (stage 1 stop point, 284 u off) and
`runs/gv2/l2st2b_0_0.rkg` (boost, misses the ramp). Tool change: `tools/gv2_tail_evolve.py` got `--sync-y-from` (height in
the sync distance; backup `tools/gv2_tail_evolve.py.bak-gv2`).

**Next for the lap 2 entry:**
- The bounce is the real precision step (like the L1 hit): it needs EV ~50 off the block, which no candidate reached (best 45).
  A dedicated bounce search (contact geometry around row 1026, edits in rows ~990-1026, score EV at 1032-1044 and the stop point)
  is the first thing to try.
- From a different stop point, the turnaround needs both the mini-turbo and the ramp line-up at once. A cost that scores the
  take-off (airborne and height at rows 1160-1180, checkpoint stays 0) would be a better guide than position matching.
- Note: sircorvid's 20.444 ghost has a harder L1 hit (`sircS3_0.rkg`, +3.17 f at row 866), but its EV collapses after the
  hit and its best superhop fit crosses the L1 line 1.89 f behind the 27.818 (see the next section). A stays the base for the lap 2 entry.

## sircorvid's 20.444 ghost: L1 hit search (2026-11-04)

Base: sircorvid's `rGV2_20.444s_3a21391.rkg` (Discord, 10/09/2026 9:33 PM; copy at `runs/gv2/sircorvid_20.444.rkg`).
Its run-up is 2-3 f ahead of the 27.818 (+3.1 f at row 780, +1.6 f at row 844), on the line (|lat| < 35 u), and it touches the
block at row 844, but with a weak bounce (EV 33.7 at contact, 9.1 at row 850) and ends up -2.2 f behind / 450 u off at row 866.
Search: `tools/gv2_hit_evolve.py --w-pace 0` (the pace penalty would drag the run-up back to the 27.818's pace), pop 2048, p-y 0.85,
4 runs (`runs/gv2/sirc_hit.sh`, log `sirc_hit.log`, ~1 min each). All CPU-verified.

| candidate | edits | contact row | EV at contact / 850 | yaw at contact | ahead at 866 / 876 | lat at 866 |
|---|---|---|---|---|---|---|
| 27.818 | - | 846 | 62.5 / 44.3 | -118.1 | 0 / 0 | 0 |
| A's hit (`gv2_L1hit_A`) | 3 | 845 | 61.6 / 56.1 | -114.7 | +0.84 / +0.85 f | -68 |
| **S3** `runs/gv2/gv2_L1hit_sircorvid_S3.rkg` | **3** (stick Y at input 605, 613, 655) | **842** | 66.0 / 54.9 | -109.1 | **+3.17 / +3.18 f** | +62 |
| S2 `runs/gv2/gv2_L1hit_sircorvid_S2.rkg` | 7 | 842 | 64.0 / 51.5 | -109.5 | +2.87 / +2.88 f | +150 |
| S1 | 12 | 842 | 69.3 / 61.4 | -106.0 | +1.82 / +1.14 f | +324 |

**But it does not carry to the L1 line.** Superhop fit (`tools/gv2_tail_evolve.py`, same settings as the A fit, seeded with A's
hops shifted 0-4 frames and a 27.818 splice; then again with an EV reward at rows 880-940, and a joint fit over rows 800-1000):
best L1 line **+1.89 f behind the 27.818** (`runs/gv2/gv2_L1hit_sircorvid_S3_superhops.rkg`, line 977.40), vs A's -1.28 f.
Logs: `sirc_fit.log` (tail shift 1: +1.91 f, shift 3: +2.12 f), `sirc_fit2.log` (EV reward +1.89 f, joint +1.90 f).
Why: S3's EV collapses from 38.5 at row 866 to 19 at 876 and stays ~20, while A and the 27.818 keep EV ~40 to the line; S3's
+3.2 f is gone by row 910 (+0.3 f) and it ends -1.9 f at row 976. None of the three fits could keep the EV, so the cause is
most likely the hit itself: S3 hits the block at a very different angle (yaw -109 at contact vs -118 / -115).
**A stays the best L1.** Possible next try: a hit search on this ghost that also scores EV at row ~880-900 (with a fitted tail
frozen after the hit), to find a contact angle whose EV lasts.

### Follow-up: hit search scored on EV lasting (2026-11-04)
`runs/gv2/sirc_hit2.sh` (log `sirc_hit2.log`): `tools/gv2_hit_evolve.py` with the S3 + superhops run as the base (so every
candidate hit is followed by fitted superhop inputs), edits in rows 771-846 (one run from 740), scored on ahead at rows 900/920
(one run 880-940) + EV at row 880 + a penalty for > 60 u off the 27.818's line after the hit (`--w-postlat 1 --postlat-tol 60`),
3 runs x 300 gens, one seeded with S1/S2. **No candidate beat S3 itself**: the best stays S3 (EV 13.6 at row 880, +1.25 f at row
900). Without the off-line penalty, 1 edit gave "+3.5 f at row 900" by leaving the line by 411 u (not a usable path).
So on this ghost, no small stick change before the hit both keeps the run-up lead and gives a bounce whose EV lasts; A stays the best L1.

### Follow-up: S3 with the missing hop (2026-11-04)
A and the 27.818 hop again ~20 rows after the hit (B re-press at rows 871 / 870); S3's fit holds B from 848 to 881, stays on the
ground and its EV decays 38 -> 14 by row 880. Adding a one-frame B release at row 868 (`runs/gv2/_s3hop_868.rkg`) keeps the EV
(36-40 through row 881, like A). Fits (`sirc_hopfit*.sh/log`):
- hop as a seed or as the base, edits from 849: the search just deletes the hop again (back to +1.89 f).
- hop locked (edits from row 870), `runs/gv2/sircL868_0.rkg`: **lead +3.6-3.7 f through rows 896-916 (A: +1.2)**, but the kart is
  carried off the line (+155 u at 896, +304 at 916, +1800 at 976) and ends **+3.06 f behind** the 27.818 at the L1 line.
- same with line penalties every 10 rows from 890 (`sircM868_0.rkg`): +3.04 f, no change.
Reading: S3's EV points off the 27.818's line (S3 meets the block at yaw -109 vs -118 / -115), so S3 can either keep its EV and be
carried off the line, or stay on the line and lose the EV. Neither beats A. Fixing it needs a different contact angle, which the
small-edit hit searches did not find. **A stays the best L1.**

### Follow-up: forcing an A-like contact angle (2026-11-04)
`tools/gv2_hit_evolve.py` got `--yaw-contact-target/--w-yaw-contact/--yaw-contact-tol` (cost per degree of |yaw at the contact
row - target|; backup `tools/gv2_hit_evolve.py.bak-gv2`). Base = S3 + superhops, contact allowed in rows 842-847, off-line penalty
on (`--w-postlat 1 --postlat-tol 60`). Logs `sirc_yaw.log`, `sirc_yaw2.log`.
- Target -115 (A) / -118 (27.818) at 20 per degree, budget 10-16, edits from 771 or 740 (4 runs): every run keeps S3 (yaw -109.1).
- Target -115 at 200 per degree, budget 20, from 740 (`sircY5_0.rkg`): reaches yaw -116.0, but only by touching the block at
  row 844 instead of 842, with EV 27.5 at row 850 and **-0.77 f** at row 866 (S3: +3.17 f). That is close to sircorvid's
  original hit again (row 844, yaw -119.6, EV 33.7).
So on this ghost the contact angle follows the contact row: hitting at 842 gives the strong bounce at yaw -109 (EV carried off
the line), hitting at 844 gives an A-like angle but a weak bounce. No small stick change gives both. **A stays the best L1.**

### Follow-up: longer searches (2026-11-04, ~75 min of GPU time)
All lap 1 line times are from CPU dumps (`runs/gv2/*_cpu.csv`), measured against the 27.818's line at 975.51.
- **Edits further back** (`sirc_early.sh/log`, 2 x 12 min, pop 2048, budget 30): run-up edits from row 600 (X1) and row 660 with
  more steering (X2), A-like contact angle (target -115, 50 per degree), contact only at rows 842-843 so the early hit is kept.
  Both stayed exactly on S3 (0 edits, yaw -109.1). About half of every generation moved the contact out of 842-843.
- **Steering after the hit** (`sirc_steer.sh/log`, 2 x 12 min): edits from row 850 on the S3 + hop fit (`sircM868_0`).
  Z1 (heavy line penalty, `sircZ1_0.rkg`): on line (11 u excess), line 977.34 = **1.83 f behind**. Z2 (sync to the 27.818 two
  frames ahead at rows 960-1000, `sircZ2_0.rkg`): 1.85 f behind, still 86-377 u from that target. Only 0.06 f better than S3 + superhops.
- **Run-up edits scored at the line** (`sirc_line.sh/log`, 2 x 12 min): edits from row 700, contact anywhere in rows 842-846, scored
  on ahead at rows 956-974 with the post-hit inputs fixed. W1 (post-hit = Z1, `sircW1_0.rkg`): 1 edit, **1.87 f behind**. W2 (post-hit =
  the hop fit): no valid candidate (off the line), 3.04 f behind.
Note: `gv2_tail_evolve.py` prints "L1 line +x f vs 27.818" as candidate minus 27.818, so a positive number means behind.

**Conclusion for this ghost:** best lap 1 line is 1.83 f behind the 27.818 (`sircZ1_0`), against A's 1.28 f ahead, a gap of ~3.1 f.
Edits before the hit can't change the contact angle without losing the early hit, and edits after it can't turn S3's sideways
bounce into speed along the line. **A stays the best L1.** Only the splice of sircorvid's start onto the PENDING run-up is untried.

## Route 2: the final stretch (lap 3 hit to the finish) on the 27.818 (2026-11-05)
Idea: a gain after the last ultra shortcut counts at the finish with nothing left to survive. The 27.818's lap 3 is shaped like
lap 1: block hit at **row 1888** (no B held in the run-up, B pressed at 1889), a backward bounce with EV 51-62 for ~60 rows, a
second near-touch of the block area at ~1948, then superhops at ~115 speed to the finish at **row 2078.394** (completion 4.0;
the rkg has 2080 input rows). Tool change: `tools/gv2_tail_evolve.py` got `--line-comp` (2.0 = L1 line, 4.0 = finish) and
`--cross-after` (backup `tools/gv2_tail_evolve.py.bak-gv2-fin`). All finish times below are from CPU dumps.

| stage (log in `runs/gv2/`) | what | result |
|---|---|---|
| `fin_hit.log` (4 x 2.5 min) | hit search on the 27.818, edits rows 1813-1888 (H4 from 1780), contact 1882-1894 | +0.30-0.40 f at contact +20/+30, contact still 1888, EV@1892 51.6. With the 27.818's later inputs **none finishes** (completion stalls at 3.93) |
| `fin_fit.log` (3 x 7 min) | superhop fit rows 1889-2079 on H2/H4/H1, scored on the finish | none finishes (~0.014 completion = ~18 f short) |
| diagnosis (`finH2_0_cpu.csv`) | H2 vs the 27.818 | identical bounce, +0.79 f at row 1940, but **H2 touches the block again at row 1948** (0x400), EV 38 → 9, 16 f behind by 1996 |
| `fin_fit2.log` (3 x 7 min) | edits 1889-1962 only, EV reward at 1950-1968, ahead at 1975, 27.818's tail shifted 0/1 | none finishes (best 1.0 f behind at 1975, 680 u off line) |
| `fin_tail.log` (3 x 7 min) | superhop fit on the **unchanged 27.818**, edits from 1950 / 1990 / 1889 | all three converge on the same single edit: **finish 2078.365 = 0.030 f (0.5 ms) earlier** |

**Result:** `runs/gv2/gv2_fin_27818_E1.rkg` (CPU dump `_cpu.csv`, edit `_edits.csv`): one edit, input frame 1828 (row 2000), stick X
+7 → +1. It finishes 0.030 f ≈ 0.5 ms ahead of the 27.818. That may not change the displayed time (27.818 → 27.817 or 27.818,
depending on how the game rounds). It's the only real, finishing gain found so far, but it's tiny.
**Reading:** the 27.818's superhops after row 1950 are already near-optimal for small edits, and the lap 3 bounce is chaotic: a
0.3 f better hit puts the kart into the block again at 1948. A better lap 3 hit needs a fit that specifically avoids that second
touch (e.g. a cost on the 0x400 flag in rows 1940-1955) before anything else.
