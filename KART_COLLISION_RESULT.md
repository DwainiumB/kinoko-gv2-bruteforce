# Kart-to-kart collision: result

Session of 2026-10-30/31 (Opus). Nothing committed. Task: `KART_COLLISION_TASK.md`.

## Summary

| step | status |
|---|---|
| 1. Decompile `0x8056F7F0` and callees | Done. Annotated pseudo-C in `docs/kart_collision_decomp.md`. |
| 2. Port into `KartCollide`, rebuild | Done. Approximation removed; game's function ported with its helpers and its real call position. Native host and web module rebuilt (now `?v=20`). |
| Follow-up: slipstream and other VS behaviour | Done (second pass, below): slipstream, engine class (50/100/150cc), VS start grid places. |
| Single-kart ghosts unchanged | Yes, after both passes: all 56 `samples/*.rkg` + `.krkg` pairs sync to their full frame count (all 55 STATUS.md cases plus one extra), and the 13-case `build/testCases.bin` suite passes. |
| 3. Frame-exact check against Dolphin | **Not done. Blocked**: Dolphin was not running, and no two-player split-screen recording exists. The diff against the real game is **unmeasured**. Tooling for it is ready (below). |

So: the port follows the game's code instruction by instruction as far as I can read it, but it has not yet been shown frame-exact against the game. The first real recording may still show differences (see "Expected sources of difference").

## What the game actually does (and what the old approximation got wrong)

Details and offsets: `docs/kart_collision_decomp.md`. The main points:

1. **Where it runs.** `KartSub::calcPass1` searches its BoxColUnit with flag `0x1F` and calls `checkPlayerCollision`
   once per *driver unit* the search returns (`BoxColManager::getNextPlayer` `0x80785D8C`), **before**
   `calcObjectCollision`. Kinoko called its approximation after object collision, looping over every racer.
2. **Once per pair per frame.** `KartState+0x84` is a u16 mask of players already handled; both karts' bits are set, and
   `KartObjectManager::calc` clears every kart's mask at the start of the frame (together with tangentOff/movement).
   So kart 0 (which runs first) usually handles the pair and writes into kart 1's state.
3. **Overlap.** Every body hitbox pair is tested; zero-initialised min/max boxes collect `(unit dir to other) * depth`
   and the contact points (`0x8056EEF4`). Push direction = `min + max`, normalised; its length is the overlap.
4. **Separation.** Each kart is moved half the overlap apart through `tangentOff` and `movement` (no velocity involved).
5. **Items first.** Bullet vs no bullet, then star vs no star, then mega vs no mega decide by starting KartAction 6, 3 or
   13 on the loser (with `hitDepth`) instead of a bump. Team mates always just bump.
6. **The bump** (`0x80570DA8`, applied to each kart that is not in a bullet and whose bump timer is 0):
   - `strength = min(100, (w_source / w_target) * (3 + 0.11 * |speed_source|))` (weights raised by slipstream boost,
     scaled 1.5 / 0.5 by mushroom or boost panel boosts, both on the source weight; first misread as trick / zipper, corrected in `DOLPHIN_VERIFY_RESULT.md`);
   - a force along the target's sideways axis (pushDir projected on the kart's right vector, made perpendicular to its
     travel direction, then flattened against its smoothed up vector), `* 0.2` over a zipper, `* 0.5` after 20 frames
     of airtime, applied with `addForce` and `applyWrenchScaled` at a point `0.3 * (1 + weightClass) * boundingRadius`
     from the target's centre;
   - speed: `|v| -> max(|v| - 0.5 * strength, 0.5 * |v|)`, sign kept;
   - a spin kick `angVel0.z += +/-0.05 * strength`;
   - `playerBumpTimer = 10` (decremented once per frame in `calcPass1` after `calcFloorEffect`), floor moment rate
     restarted at 0.01, status bit 56 set.
   - Quirk kept on purpose: the weight class and bump deviation level come from the kart whose `calcPass1` found the
     pair, for **both** targets.
7. **Bikes.** A bike in a wheelie starts a 25-frame yaw wobble (`0x80579F6C` / `0x80579FE4`, now
   `KartMove::startWheelieBumpWobble` / `calcWheelieBumpWobble`, called from `KartMove::calc`), and every bike involved
   loses its wheelie (KartMove vtable `+0x30`, now `KartMove::onPlayerBump`).

The old approximation (one push of `6 * 2 * weightShare` along the deepest sphere pair, no speed loss, no timer, no
position split, wrong call order) is gone.

## Kinoko-only measurement (not compared with the game)

Two karts (Mario, Standard Kart M), Luigi Circuit, kart 1 steering into kart 0 (new `versus` host mode). Contact at
race frame 355; the bump timers, speed losses and spin kicks appear exactly as the decoded formula predicts:

| race frame | kart | speed | playerBumpTimer | angVel0.z |
|---|---|---|---|---|
| 354 | 0 | 31.395 | 0 | -0.0002 |
| 354 | 1 | 64.863 | 0 | 0.0009 |
| 355 | 0 | 25.875 | 9 | 0.4890 |
| 355 | 1 | 62.195 | 9 | 0.3655 |
| 363 | 0 | 21.422 | 1 | 0.2937 |
| 364 | 0 | 20.929 | 0 | 0.2649 |

(Formula check for kart 0: strength from kart 1 = 3 + 0.11 * 64.86 = 10.13, speed 31.40 - 5.07 = 26.33 before that
frame's own coasting; timer shows 9 because the same `calcPass1` decrements it after setting 10.) The native build and
the wasm build produce identical positions for these frames.

## Step 3: what is ready and how to run it

Nothing below has been run against the real game yet.

- `scripts/kart_collision_logger.lua` (DolphinLuaServer-mkwii-lan) now also logs, per racer: `bump_timer`
  (KartCollide+0x18), `pair_mask` (KartState+0x84), the 5 status words, physics `pos`, `ext_vel`, `ang_vel0`,
  `full_rot` (KartDynamics +0x68, +0x74, +0xA4, +0x100) and 16 raw words of the racer's KPad
  (RaceManager +0x0C [i] +0x48). Additions only; the existing fields are unchanged. Not run yet.
- `kinoko_host versus --course <id> --kart <char>:<veh> --kart <char>:<veh> --inputs <file> --out <csv>`
  (`source/host/KVersusSystem.*`) runs a multi-kart race from per-race-frame inputs and writes position, full
  rotation, speed, bump timer, extVel and angVel0.z per kart per frame.
- `tools/kart_collision_diff.py inputs dump.json in.txt` extracts both karts' inputs from the dump;
  `tools/kart_collision_diff.py diff dump.json kinoko.csv` prints, per kart and field, the first race frame that
  differs. Round-trip tested (Kinoko output -> fake dump -> inputs -> Kinoko -> diff: 778 kart-frames, no difference;
  a run with other steering is flagged at the first changed frame).

Steps for the user:
1. Dolphin with the PAL disc, two controllers (port 1 and 2), Multiplayer -> 2 players -> VS, items off, no CPUs.
   Record a DTM while driving the scenarios (side bump at matched speed, rear-end, heavy vs light, bike in a wheelie,
   holding station side by side), so the race can be replayed.
2. Replay the DTM with `out.exe -s scripts\kart_collision_logger.lua -d karts2p.json` attached; Ctrl+C at the end.
3. Check the KPad layout once: in the dump, the words at byte offset `--state-offset` (default 8) should hold
   buttons (u16 at +4: accelerate 1, brake 2, item 4, drift 8) and the stick as two floats at +8/+0xC in steps of 1/7.
   Adjust `--state-offset` if not.
4. `python tools\kart_collision_diff.py inputs karts2p.json in.txt`, run `versus` with the two characters/vehicles,
   then `diff`. The first differing frame/field points at the cause.

## Expected sources of difference (before any collision code is involved)

- Slipstream is now ported (second pass), but like everything here it is checked only against the decoded game code,
  not against Dolphin.
- Start grid placement and the second kart's setup in a 2-player split-screen race have never been compared; Kinoko's
  VS mode marks host-driven karts as `Cpu` type.
- Items, teams and battle mode are not in Kinoko; the star/mega/bullet branches are ported but cannot fire (Kinoko's
  handlers for actions 6 and 13 are stubs).
- Status bits 40, 72, 82, 89 (collision blockers, named `NoKartCollision40` etc.) are never set by Kinoko; their game
  roles were not identified.
- Not ported because they do not touch kart physics: sparks, model shakes, driver animations, sounds, rumble, CPU AI
  notify, per-kart hit counters, item hooks (`0x8079A578`, `0x80798B28`), battle balloon steal and scoring.

## Files changed (all uncommitted)

- `source/game/kart/KartCollide.cc/.hh`: `calcPlayerCollision` (0x8056F7F0), `IsPlayerCollisionDisabled` (inlined),
  `checkPlayerHitboxOverlap` (0x8056EEF4), `applyPlayerBump` (0x80570DA8), `calcPlayerBumpTimer` (0x805713B8),
  `m_playerBumpTimer`; `calcKartCollision` removed.
- `source/game/kart/KartSub.cc`: search flag includes drivers, kart-kart loop before object collision, bump timer
  countdown between `calcFloorEffect` and `calcFloorMomentRate`.
- `source/game/kart/KartObjectManager.cc`, `KartState.cc/.hh`: per-frame pair mask.
- `source/game/field/BoxColManager.cc/.hh`: `getNextPlayer` and its iterator.
- `source/game/kart/KartMove.cc/.hh`: wheelie bump wobble, `onPlayerBump` (bike: cancel wheelie).
- `source/game/kart/KartBoost.hh`: `active(Type)`. `source/game/kart/Status.hh`: names for bits 40, 56, 63, 65, 66, 72,
  79, 81, 82, 83, 89, 91, 134.
- `source/host/KVersusSystem.cc/.hh`, `source/host/main.cc` (`versus` mode), `tools/kart_collision_diff.py`.
- `docs/kart_collision_decomp.md`, `web/kinoko_web.js/.wasm` rebuilt, `web/index.html` `?v=19`.
- Outside the repo: `kart_collision_logger.lua` extended (see above).

The user's pre-existing uncommitted edits were left as they were (`KartMove.hh` `smtCharge()`, `FrameState.cc`,
`main.cc` mode list, `web_bridge.cc`, `CMakeLists.txt`, `index.html`); my edits to `KartMove.hh`, `main.cc` and
`index.html` only add lines next to them.

## Reverse-engineering setup (reusable)

Scripts are in the shared notes folder `kart_collision_re/` (no game data in them): `mkw_image.py` builds an ELF of
PAL memory (main.dol + StaticR.rel relocated at its real base `0x805102E0`; em-eight's addresses are the real ones),
`pspatch.py` rewrites paired-single opcodes for stock Ghidra, the Ghidra scripts set r2/r13, apply em-eight names,
fix the false no-return on `normalise` and decompile. Headless import + analysis takes about 2 minutes with the
Ghidra 12.1.3 + JDK 21 from the MKDS toolchain.

## Second pass: slipstream and other VS / multiplayer behaviour

Method: listed every kart-code function that reads another racer or the race config's game mode, engine class,
course or team fields, and every test of the slipstream status bits (details in `docs/kart_collision_decomp.md`,
"Other VS / multiplayer behaviour"). Battle, mission, awards, rumble, camera, sound and UI readers were set aside.

Ported:
- **Slipstream** (`KartMove::calcSlipstream` 0x80586FA8, `clearSlipstream` 0x80582488): a 12-slot round-robin in
  RaceManager (one racer searches per frame, whatever the player count), a 1000-unit sphere 1000 units behind the
  racer ahead plus a 0.982 (kart) / 0.99 (bike) cone, both at >= 0.5 speed ratio; 90 frames of charge, 135 frames of
  boost with acceleration 0.7 and boost speed limit >= 115; reset in `clear`, `initOob` and `enterCannon`.
- **Engine class**: `RaceConfig::Scenario::engineClass` (default 150cc), `KartMove::m_engineSpeedFactor`
  0.8 / 0.9 / 1.0 / 0.7 applied to base speed, the boost speed limit and the jump pad check; `ObjectPillar` and
  `ObjectVolcanoPiece` pick their engine-class settings.
- **Start grid**: `RaceConfig::Player::startPlacement` (0 = index + 1) feeds `RaceManager::findKartStartPoint` as the
  game's VS placement does.
- Options: `kinoko_host versus ... --cc 50|100|150 --start 2,1`; web `kinoko_set_vs_options(engineClass,
  placements, count)` before `kinoko_init_vs` (Time Trial init resets it to 150cc / index places).
- Logger: also logs engine class and each racer's place; the diff tool also compares the slipstream state.

Kinoko-only measurements (Luigi Circuit, Mario + Standard Kart M x2, inputs from a small closed-loop planner that
steers kart 1 into kart 0's wake):

| race frame | kart 1 slipstream | kart 1 speed | kart 0 speed |
|---|---|---|---|
| 325 | first charging frame | 47.066 | 51.217 |
| 590 | charging (last) | 76.766 | 79.770 |
| 591 | boost starts | 77.466 (+0.70) | 79.770 |
| 599 | boost | 83.066 (+0.70 / frame) | 79.770 |
| 641 | boost | 112.469 | -14.171 (hit a wall) |

Top speed by engine class (kart 0, race frame 440, accelerating from the start): 150cc 78.852, 100cc 71.793
(capped at 0.9 x 79.770), 50cc 63.816 (0.8 x). `--start 2,1` swaps the two karts' grid positions. The wasm build gives
the same 100cc position as the native build at the same frame.

Checked and not needed for VS kart physics: the KartObjectManager mode flags (course- and award-mode-only), teams
(not in Kinoko), Lakitu and camera (visual only; respawn physics already reads each player's respawn point).

Still not in Kinoko (each is a project of its own): items and every item effect (star, mega, bullet, thunder cloud,
shock, ink; the ported collision and speed code has their branches noted but not added), mirror mode, battle mode,
CPU AI, online netcode, and the engine-class object at `0x806E3A8C` (not ported at all).

Files changed in the second pass (uncommitted): `Status.hh` (bits 64, 135), `RaceConfig.cc/.hh`, `RaceManager.cc/.hh`,
`KartMove.cc/.hh`, `KartObjectManager.hh` (`count()`), `ObjectPillar.cc`, `ObjectVolcanoPiece.cc`,
`host/KVersusSystem.cc/.hh`, `host/web_bridge.cc` (`kinoko_set_vs_options`), `tools/kart_collision_diff.py`,
`docs/kart_collision_decomp.md`, `web/kinoko_web.*`, `web/index.html` (`?v=20`); outside the repo the logger.
