# rGV2 Ultra 3-lap: brute-force state (read 2026-11-04)

Source: the rGV2 UR 3lap Discord thread (2,218 messages, 08/2025 to 11/2026).
Combo: Funky Kong (char 22) + Standard Bike L (veh 20), course 25.

## Ghosts staged here
- `rGV2_27.818_slimpanda_best.rkg`: current best, 9.418 / 9.209 / 9.191 (slimpanda, 2026-10-15).
  Local Kinoko replay: lap 2 at timer 9409-9426 ms, lap 3 at 18618-18635, finished at row 2079. In sync.
- `rGV2_28.165_aoiro.rkg`: the old run without fast block hits on L2/L3 (9.447 / 9.458 / 9.260).
- `rGV2_22.000_slimpanda_L1_with_L3_movement_PENDING.rkg`: the L3 movement copied onto L1 (1049 input frames).
  This is the job sam never ran. Inputs split from the 27.818 at dump row 661 (input frame 489).
  It FAILS the fast hit: at row 850 EV is 16 against 44 on the 27.818.
- `sam_L1hit_candidate_24.rkg` / `_25.rkg`: sam's L1 hit candidates 24/25 (~0.4 f ahead 20 f after the block, no superhops fitted).

rkg input frame = dump row - 172. sam's "race_frame" = input_frame - 240 (timer frames). (Corrected 2026-11-07: this note first said row - 171.)
The 27.818's fast L1 block hit is at row 846 = input frame 674 = race frame 434 (the thread's "frame 676" counts differently). The L2 contact is at race frame 988.

## What sam (fable5mkw) did
- Simulated annealing on Kinoko savestates, 28 CPU workers, edits to whole-frame inputs. Also a GPU port: ~2.7M kart-frames/s on an RTX 5060 Ti, with a ~12 KB sim-state snapshot.
- L1 v2: 34 edits at timer frames 401-559 (mostly stick Y, plus B taps at 544-559), +1.78 f.
- His best setup: few edits, mostly vertical stick, inputs frozen after the hit (from the B release), d-pad only where needed.
  Scoring: forward progress along the reference path ~20 f after contact, plus a bonus for more right yaw, plus a pace attractor before contact.
  Final score is always the full 3-lap time after the superhops are fitted.
- A wide search space made things worse: the hits pulled ahead and the superhop sequence broke.
- How precise the hit is: 0.024 units / 0.02 u/f apart already moves the hit from 51.0 to 46.7 EV, so only lucky combinations land it.

## Open job
slimpanda's L3 hit is ~1 f earlier than L1/L2 (~0.9 f gain). Next: search the L1 hit on the PENDING ghost, then do the same on L2,
then fit the superhops (by hand or with a search) and check in Dolphin.
