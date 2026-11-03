# Item objects, part 2: result

Session of 2026-11-02 (Opus 5.5, started from the items session). Nothing committed. Builds on `ITEM_OBJECTS_RESULT.md`
(green shell, banana, held items, hits, drops) and the other uncommitted work in the tree.

## Summary

| | status |
|---|---|
| Red shell (+ triple reds) | **Ported**: thrown forward it follows the item route (ITPT / ITPH) at 130, with direct steering for 45 frames and then a Bezier spline through the next points; it looks for a racer ahead (4000 range, about 18 degree cone, height -1500..1000) and homes in (speed 50, rate 0.2); lost targets drop it into a free slide at 140. Stick down: thrown backward, breaks on the first wall. Lifetime 2400 frames. |
| Triple items, use modes 2 and 3 | **Ported**: triple bananas hang in a chain behind the kart (each link dragged behind the one before, swings out in turns, copies the first one's hop 6 frames later); triple shells circle the kart (speeding up to 1200 per frame plus the kart's speed, the circle growing to the kart's size). Each press throws one; a hit item detaches as in the game (chain: the ones behind it are released and flung up, orbit: it swaps places with the last). |
| Fake item box | **Ported**: dropped behind (1 floor bounce) or thrown forward with the stick up (3 bounces), lies on the course; a kart that touches it gets action 2 unless in a mega, star or bullet (0x8057325C). |
| Bob-omb | **Ported**: thrown forward (45, or 100 with the stick up, 3 bounces) or dropped behind with the stick down (90-frame fuse); its own sub-state machine (flying, fuse, explode); a racer closer than 8, 4, 2, 1 explosion radii cuts the fuse to 120 / 60 / 30 / 4 frames (150cc; 150 and 180 at 100cc and 50cc); the explosion grows to scale 36 (radius 1044) and gives action 7 for 30 frames, then action 0, and is gone after 86 frames. It hits its owner too. |
| Thunder cloud | **Ported**: spawned over the racer when the roulette gives it (or used from the inventory, 0x807AF1BC); sets the kart's thunder cloud status; a bump passes it to the other racer (not within 45 frames of the last pass, nor in its last 2 frames, nor to a racer respawning or in a cannon, star, mega or bullet; the strike timer is capped at 480 on a pass); strikes its carrier at 600 frames (shrink for 612 frames, action 17) and breaks 90 frames later; breaks without striking if the carrier respawns or gets a star, mega or bullet. |
| POW block | **Ported** (item and kart side): the racers ranked ahead of the user hop on the first two shakes (+6, +10, unless 20 frames in the air) and the last shake, 114 frames after use, spins those on the ground (action 11: the strong spin, with the items lost; a trick-up input in the 10 frames before, or in the first 8 of the spin, makes it the light one). |
| Blooper | **Ported**: racers ranked ahead of the user (at the end of the blooper's 70-frame `start` animation + 30) are inked one after another (148 frames later plus 3 x a per-player delay), for 450 frames. |
| Blue shell | **Ported**: on the item route (60, no wall-bounce limit, the branch search towards the target's own item point) after the leader, or the thrower itself when it leads; locks on within 8000 (5000 on Mario Circuit) and 1500 below / 1000 above; homes in, circles the target once on a shrinking circle, dives for 25 frames and drops on it; explodes on touching the course (radius 1044, action 7 for 30 frames, then action 0, gone after 86 frames). Without an item point it slides off at 85 and goes straight for the target. |
| Bullet bill | **Ported** (the `KartKiller` autopilot and KartMove's bullet path): every other effect ends; the kart flies at 145 (x the engine class factor) with its rotation turned towards the next item point each frame (faster the sharper the turn), flies 100 above points marked for it or once inside the route's corridor (no gravity), climbs or turns aside when stuck on a wall; ends after 480 frames, or after 180 once in the lead or `rank - {1,1,1,1,2,2,3,3,4,4,5,5}[players - 1]` places up, then 70 frames to finish; 120 frames against walls end it too. Its size is a mega's (hitbox and box collision) and its scale 1.5. |
| Item vs item | **Not ported** (not needed by any tested pair). |
| Single-kart ghosts | 56/56 `samples/*.krkg` pairs sync to their full frame count; 13/13 `build/testCases.bin`. |
| Dolphin VS recordings | `test1` (15818 kart-frames) and `test2` (29838) compared with `tools/kart_collision_diff.py`: **no differences**. |
| Web module | Rebuilt, `kinoko_web.js?v=30`. Not run in a browser with the new items. |

## Measurements (Kinoko only; Luigi Circuit, two Mario + Standard Kart M, `kinoko_host versus`)

Inputs: `rear_base.txt` from the items session (kart 1 follows kart 0, then passes it around frame 370 and hits a
wall at 420) plus `item` lines. Rows are race frames.

| scenario | result |
|---|---|
| Kart 1 throws a red shell at 314 (kart 0 ahead) | kart 0 hit at 348: action 2. |
| Kart 1 uses triple greens at 310, throws at 380, 420, 460 | the three shells circle the kart at 133-168 from its centre, 8-15 above it; each press throws the last one (scale 0.5 -> 2.1), the others keep circling. |
| Kart 1 uses triple bananas at 310, throws at 380, 420, 460 | they hang 159, 194 and 228 behind the kart; each press drops the last one behind. The second one lands in front of the kart after it bounced off the wall, and the kart spins on it at 448 (action 0) once its owner immunity is over. |
| Kart 1 uses triple reds at 310, throws at 380, 420, 460 | kart 1 leads by then: the shells follow the item route; the last two were thrown while kart 1 was stuck at the wall and break on it. |
| Kart 0 drops a fake item box at 320, kart 1 behind | kart 1 drives into it at 343: action 2. A banana in the same spot spins it at 347 (the box's hit radius is 145 at scale 2.5, the banana's 58). |
| Kart 1 throws a fake item box forward with the stick up at 314 | 3 bounces, slides to the wall in front and vanishes there at 435 (wall slide on a steep wall). |
| Kart 0 drops a bob-omb (stick down) at 324, kart 1 behind | kart 1 comes within one explosion radius: fuse cut to 4, explodes at 346; kart 1 gets action 7 at 349, kart 0 (its owner, 650 ahead) at 352; the bob-omb is gone at 432. |
| Kart 1 throws a bob-omb forward at 314 | lands at about 425 and explodes at 436 (fuse cut by kart 0 coming close); no kart in range. |
| Kart 1 uses a thunder cloud at 310 (no bump) | kart 1 struck at 910 (action 17, 72 frames); the cloud breaks at 1001 and is gone at 1020. |
| Kart 1 (behind) uses a POW at 310 | kart 0 hops at 326 (+6) and 374 (+10), and is spun (action 11) at 425. |
| Kart 0 (second by then) uses a blooper at 320 | kart 1 is inked at 571 (100 + 148 + 3 frames after use) for 450 frames. Kart 1 using it at 310 inks nobody: it leads by frame 410. |
| Kart 1 (second) throws a blue shell at 314 | kart 0 (the leader) is launched by its explosion at 401 (action 7); the shell is gone at 485. |
| Kart 0 (leading) throws a blue shell at 324 | it comes back for kart 0: launched at 405. |
| Kart 1 (second) uses a bullet bill at 310 | speed 145 from 311, follows the course through the first turns, is first by 325, ends at about 565 (180 + 70 frames after use, as it leads), back to normal driving after. |
| Kart 0 uses a bullet bill at 380 (second by then) | takes the lead, ends at about 631. |
| `bump.txt` (the karts bump around 354); kart 0 uses a thunder cloud at 335 | the bump passes it to kart 1, struck at 935. With kart 1 using it at 345 instead, kart 0 is struck at 945. |

## What was ported (files)

- `source/game/item/ItemObjRed.*` (new): `ItemObjRedShell` (vtable 0x808D2228), its 7-state machine (table
  0x808D2148, `calcRed` 0x807AA87C), target search 0x807B3BAC / 0x807B381C, homing 0x807B2F54, target drop
  0x807B3EC0.
- `source/game/item/ItemObjKouraRoute.cc` (new) and `ItemObjKoura.hh`: the item route follow, which is shell-base
  code in the game (fields +0x1DC..+0x27C of every shell, also called by the blue shell): 0x807B4878 / 0x807B5068 /
  0x807B4AE4 / 0x807B4944 / 0x807B4D2C, next point 0x807B91E4, the route spline 0x807B7D9C..0x807B8600. First written
  inside the red shell, then moved here; the red shell runs are byte-identical before and after the move.
- `source/game/item/ItemObjKoura.*`: shell gravity 0x807B61CC / 0x807B6148, the free slide set-up 0x807B532C.
- `source/game/system/map/MapdataItemPoint.*`: the point's second setting (used by the route).
- `source/game/item/ItemTrail.*`: use modes 2 and 3: chain init / calc 0x807931DC / 0x8079356C, orbit init / calc /
  positions 0x8079455C / 0x80794694 / 0x807941F0, detach by mode 0x80793F74 / 0x80794AB0, held growth 0x8079ED1C;
  `use` no longer refuses triple items.
- `source/game/item/KartItem.hh`: `pressRequested` (flags 0x244, the triple items' throw).
- `source/game/item/ItemObjFakeItemBox.*` (new): vtable 0x808D1D60, release 0x807A7940, flight 0x807A79E0.
- `source/game/item/ItemObjBobOmb.*` (new): vtable 0x808D1BE0, spawn 0x807A5BC4, release 0x807A4A18, break
  0x807A5F6C, drop 0x807A60F8, sub-state runner 0x807A4CDC (table 0x808D1B18: flying 0x807A4B48, fuse 0x807A43FC,
  explode 0x807A45E0 / 0x807A4734), nearest racer 0x807A5D88, explosion radius set-up 0x807A4384.
- `source/game/item/ItemObjHolder.cc`: creates the new kinds.
- `source/game/item/ItemObjThunderCloud.*` (new): vtable 0x808D2480, spawn 0x807AF234, update 0x807AF76C (its
  initial state, through 0x807A3908), pass 0x807B0B4C / 0x807B1108.
- `source/game/item/ItemDirector.*`: cloud spawn 0x8079A298 and pass 0x8079A578; `KartItem`: the roulette spawns the
  cloud instead of dropping it, cloud use 0x807AF1BC, strike 0x807987EC; `KartMove::applyThunderCloud` 0x805805EC.
- `source/game/item/ItemPowManager.*` (new, the game's `PowManager` 0x809C3640): use 0x807B1DB4, update 0x807B22F8,
  shakes 0x807B20BC; `source/game/item/ItemBlooperManager.*` (new, `GessoManager` 0x809C3610): use 0x807A81B4,
  update 0x807A92B0, targets 0x807A972C (the `start` animation length is read from `gesso.brres`). Both run from
  `ItemDirector::calc` after the slot timers, as in 0x80799850; `KartItem` use functions 0x807B1B2C / 0x807A81B4.
- `source/game/item/ItemObjBlueShell.*` (new): vtable 0x808D23D8, spawn 0x807ABF70, release 0x807AC634 / set-up
  0x807AC49C, break 0x807AE414, runner 0x807AD118, states (table 0x808D2308) 0x807AD5A4, 0x807AD5EC, 0x807AD7E4 /
  0x807AD824, 0x807AD914 / 0x807AD958, 0x807ADB54 / 0x807ADC5C, 0x807ADF14 / 0x807ADFA4, 0x807AE180 / 0x807AE34C,
  target choice 0x807AC1A8, lock-on 0x807B45B0, homing 0x807B3FDC (entries 0x807B43DC / 0x807B4400), descent
  0x807B4430, height 0x807ACB24, orientation 0x807ACE1C, squash 0x8079FD84. The shared route code takes the blue
  shell's arguments (bounces, floats, branch search: 0x807B91E4 with the search on); the red shell runs are
  byte-identical before and after.
- `source/game/kart/KartKiller.*` (new): start 0x8059B7B8, update 0x8059BC44, cancel 0x8059C118, up axis 0x8059D0C0,
  aim 0x8059D44C, next point 0x8059C29C, steering 0x8059C44C (quaternion product 0x8059C798), lift 0x8059D658, end
  0x8059CC60, walls 0x8059C888, Rainbow Road fall check 0x8059DCDC, corridor 0x8059DAE4 / plane 0x8059D97C, point
  flags 0x8059D2D4; created by `KartSub`, reached through the kart accessor (`killer()`).
- `source/game/kart/KartMove.*`: the bullet path of `calc` (0x805788DC: top, jump pad end, pads, dirs, the killer,
  sticky road, offroad, manual drift, scale, cannon, ink, acceleration; no rotation), `calcTop`'s bullet branch,
  `calcAcceleration`'s fixed speed (0x8057B9BC), `activateBullet` 0x805858AC, the effect clear 0x805837CC, the bullet
  scale (+0x180) in the total scale (0x8058160C), the cancels in 0x8057829C and 0x80583658; `KartDynamicsBike`
  stabilises like a kart in a bullet (+0x174, 0x805B6448); item points read their width and first setting;
  `KartItem::useBullet` 0x807A9AFC.
- `source/game/kart/KartAction.*`: action 11 (the POW spin: start 0x80568064, calc 0x805683B8, end 0x80568620,
  dodge 0x80568558) and the POW strike globals (0x809C1898: start 0x805674FC, countdown 0x80567594 at the end of
  `KartObjectManager::calc`, reset 0x80567578, per-kart flag +0xF8); `KartMove::calcPow` 0x805810A8 (between the
  boosts and the mega / star / shock block of `KartMove::calc`).
- `source/game/kart/KartCollide.cc`: item hit handlers for the fake item box (0x8057325C) and the bob-omb
  (0x805731C8); the bump (0x80570DA8) passes a thunder cloud.

## Approximations and gaps

- No driver model: items start their release from the kart's position, not the hand (as before).
- KartItem +0x240 (an item immunity timer) is not ported and taken as 0 (red shell target search, bob-omb nearest
  racer).
- Red shell: state 5 (online homing) is not ported; the round-robin target search is treated as always allowed.
- Bob-omb: the model's up vector is kept while it flies (the explosion starts one collision radius below it), but not
  while it lies on the floor or falls after a hit, where the game's landed / dropped code updates it (visual code in
  Kinoko): on a slope the explosion centre can be off by up to its collision radius (90). The explosion's effect on the
  course at frame 10 (0x8078DB10) and flags2 bit 19 at frame 42 are not ported.
- Battle team checks (fake item box, bob-omb) are left out.
- The thrown-callback (+0x30) and dropped-callback (+0x34) of the objects only run for online-spawned objects
  (0x80796F70 / 0x807A31C0) and are not ported.
- Sounds, effects, models, the bob-omb's blinking and swell are left out.

## Not done

- Thunder cloud: its position is visual only (no collision radius) and is simply kept 600 above the carrier; the
  inventory clean-up through KartItem +0x1A, the carrier's rumble and the online transfer are left out.
- Blue shell: `1 - e^(-x/500)` in its height (0x807DF7B4) uses `std::exp`, which may differ from the game's in the
  last bit; KartItem +0x238 of the target (not ported, taken as 0) would also make the dive low; the explosion's
  effect on the course at frame 10 (0x807A61F8) is not ported; the model, HUD warning and camera are left out.
- Bullet bill: the effect clear 0x805837CC is rebuilt from Kinoko's clear functions (boosts, jump pad, ramp, zipper,
  SSMT, slipstream, offroad invincibility, star, mega, shock) rather than field by field; dynamics +0xC8 (a vector
  Kinoko does not model) is not cleared; the models, sounds, rumble and HUD are left out. Not checked against Dolphin
  (no recording with a bullet bill).
- POW: its HUD, rumble, screen shake and the per-racer hit counter (0x805918E0) are left out; status bit 130 (never
  set in Kinoko) would also cancel something on a dodge (0x805917F4).
- Blooper: the game keeps the blooper busy until the local screens' blooper models finish animating; Kinoko frees it
  once the last racer is inked, so a second blooper used in that gap starts in Kinoko but not in the game.
- Item-vs-item collision (0x807A1ED8 and the pair responses).
