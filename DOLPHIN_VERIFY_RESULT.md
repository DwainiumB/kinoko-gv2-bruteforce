# Dolphin vs Kinoko: two-player VS, frame by frame

Sessions of 2026-10-31 and 2026-11-01 (Opus 5.5). Nothing committed. Compares Kinoko's multi-kart code (kart-kart collision,
slipstream, VS grid, items: see `KART_COLLISION_RESULT.md`, `ITEMS_RESULT.md`, `ITEM_BOXES_RESULT.md`) with real
two-player split-screen races of the PAL game (RMCP01) recorded in Dolphin.

## Recordings and results

| recording | setup | race frames compared | result |
|---|---|---|---|
| `test1` | Luigi Circuit, 150cc, items off. P1 Mario + Standard Kart M (grid place 2), P2 Luigi + Standard Kart M (place 1). 6 kart-kart bumps (race frames 932, 942, 1125, 1324, 1805, 2085), side and rear contacts, one kart nearly stopped when hit. No slipstream. | 0 to 7908, both karts (15,818 kart-frames; the movie ends near frame 2341, after that both pads are neutral) | **Identical** after the fix below: position, full rotation, speed, extVel, angVel0.z, bump timer and slipstream state equal as single floats on every frame. Before the fix: first difference at race frame 932 (first bump). |
| `test2` | Luigi Circuit, 150cc, items off. P1 Bowser + Flame Flyer (grid place 2), P2 Baby Peach + Bit Bike, manual (place 1); seeds 0xDB5B4DBB:0x9BB4. 20 bumps, one slipstream (below). | 0 to 14919, both karts (29,838 kart-frames; frame 5605 missing from the dump, see below; the movie ends near frame 14812) | **Identical** after fixes 2 to 4. Before: first difference at race frame 6590 (boost bump), then 11915 and 11918 (wheelie bump). |
| `test3` | Luigi Circuit, 150cc, **items on (Basic)**. P1 Mario + Standard Kart M (place 2), P2 Luigi + Standard Kart M (place 1). The replay desynced from the race as driven (Dolphin movie), so the race is whatever the replay produced; the comparison is still valid (the logger records the inputs the game used). | 0 to 6713 stepped cleanly (single-frame gaps at 6129, 6146, 6157); 6713 to 8431 Dolphin ran free (unusable); stepped again after 8431 with 16 one-frame gaps | **Identical over the whole stepped range** (13,422 kart-frames, 2026-11-02) after the fixes below: items handed out, roulettes, a fake item box and two bananas dropped, a banana bouncing off a banana, a kart spinning on a banana, both karts' positions, rotations, speeds and timers. Item objects: 8,994 of 11,435 object-frames bit-exact; the rest are the first ~15 frames of each held item (below). |

| `test4` | Luigi Circuit, 150cc, items on (**Strategic**, item mode 2). P1 Mario + Standard Kart M (place 2), P2 Luigi + Standard Kart M (place 1); seeds 0xA5852924:0x01005252. Items used: green shells (one triple), mushrooms (one triple), bananas thrown forward and dragged; 16 karts hit by shells / bananas (actions on P1 at 2470, 3059, 3869, 4395, 5170, 6387, 17779; P2 at 749, 2055, 6574, 7566, 8141, 8521, 9890, 12205, 18424). | 0 to 18554 stepped (single-frame gaps at 1474, 7594, 11014, 15334); 18555 to 20470 Dolphin ran free (unusable); stepped again to 22403 | **Identical over 0 to 18554** (36,850 kart-frames, 2026-11-03) after the fix below. Before: first difference at race frame 17779 (P1 hit one frame late by a dragged banana). Item objects: 13,004 of 15,400 object-frames bit-exact (below). |
| `test5` | **DS Delfino Square**, 150cc, VS, items on (Basic, item mode 0), wooden boxes. P1 Mario + Standard Kart M (place 2), P2 Luigi + Standard Kart M (place 1); seeds 0x71F4992B:0x01003249 (the value at RaceConfig +0xB94 in this dump, 0x37E4E46C, is not the race's seed; the Opus commit session recovered the right one). Seven wooden boxes broken by karts, items dropped by boxes (mushrooms, a banana), a mushroom that fell off the course, P2 falling off the course and respawning at 9200. | 0 to 11085 stepped (single-frame gaps at 577, 3277, 3997, 10117); the movie ends near 11085 | **Identical over the whole recording** (22,164 kart-frames, 2026-11-03) after the six fixes below; item objects 10,777 of 10,777 object-frames bit-exact. Before: first differences at 7001 (box-dropped mushroom), 8341, 9199 (item fixes by the commit session), then 9200 (respawn position). |

### What `test2` contains (from the dump)

| scenario | happened? | race frames |
|---|---|---|
| Slipstream | **Yes**, P2 (bike) behind P1: charge from 5521 (97 logged frames, 5605 is the missing one), boost bit set for 136 frames, 5619 to 5754 (P1 charged 12 frames, no boost). | 5521 to 5754 |
| Side bumps at matched speed | **Yes**: 10226 (84.0 vs 75.5, headings 0.95 apart, contact from the side), plus slower side contacts at 8311, 8381, 10197. | |
| Bike in a wheelie hit | **Yes**: P2 in a wheelie at 80.2 hits P1 (stopped) at 11914; wobble bits 66 / 68, wheelie cancelled. P2 tapped wheelie again during the wobble (11917). | 11914 to 11939 |
| Holding station / pushing | **Partly**: P1 pushes the stopped P2 side-on, 11 bumps 10 to 21 frames apart (each one as soon as the 10-frame bump timer allows). Not two karts side by side at speed. | 13233 to 13589 |
| Rear-end | **Yes**: 2712 (P2 at 58.9 into P1 at 24.7, same heading) and 12567 (P1 at 88.8 into the stopped P2). | |
| Also | 6590: P2 at 115 in a mushroom / boost panel boost (KartMove +0x118 & 4) head-on into P1 rolling backwards. Heavy vs light throughout (Bowser / Flame Flyer vs Baby Peach / Bit Bike). | |

## What was fixed

1. **KartObjectManager::calc order** (`source/game/kart/KartObjectManager.cc`, 0x8058FFE8). The game runs three
   loops: reset every kart's pair mask / tangentOff / movement, then `calcSub` (pass 0, 0x8058EEB4) for **every** kart,
   then `calc` (pass 1, 0x8058EEBC) for every kart. Kinoko ran pass 0 and pass 1 per kart in one loop, so a push that
   kart 0's collision (pass 1) gave kart 1 reached kart 1's dynamics in the same frame; in the game it arrives one frame
   later. Seen at the first bump of `test1` (frame 932): kart 1's extVel.x was 14.26 in Kinoko, 0.0003 in the game,
   which shows 14.19 at frame 933. Single-kart races cannot see this, so the ghosts never caught it.
   After the fix: 56/56 `samples/*.krkg` pairs sync to their full frame count, 13/13 `build/testCases.bin`, web module
   rebuilt (`?v=25`).
2. **Boost check in the bump** (`KartCollide::applyPlayerBump`, 0x80570E98). The game scales the source weight by 1.5
   / 0.5 when the source / target is in a boost tested as `KartMove +0x118 & 4`. The earlier decode read that bit as
   the trick / zipper boost; it is the **mushroom / boost panel** boost (the mask holds boost type t at bit 2t: 0x1 is
   set by mini-turbos, start and respawn boosts, 0x4 by `activateMushroom` and the boost panel code in `KartMove::calc`,
   0x10 by `landTrick` and `activateZipperBoost`). Seen at `test2` frame 6590: P2's speed after the bump 113.333 in the
   game, 111.666 in Kinoko (strength 3.33 vs 6.67), P1's spin kick 1.5 times Kinoko's.
3. **Wheelie after a wheelie bump** (`KartMoveBike::calcWheelie`, 0x805885A8). While the bump wobble (status bit 66) is
   on, the wheelie rotation drops by a fixed 0.002 per frame instead of the slow `rotDec` ramp. Seen at `test2` frame
   11915 as a pitch rate 0.00087 rad/frame off (yaw, the wobble itself, matched).
4. **Speed limit during the wobble** (`KartMove::calcAcceleration`, 0x8057BF08). While bit 66 is on, the speed limit is
   multiplied by 0.4 (0x808B5B98) after the wall factor, so the soft limit falls by 3 per frame towards 40% for the 25
   frames. Seen at `test2` frame 11918: P2 74.859 in the game, 75.530 in Kinoko; found by logging the game's raw
   KartMove (window logger below): soft limit `+0x18` kept falling to 30.212 = 0.4 x 75.53 exactly while bit 66 was set.

After fixes 2 to 4: `test1` and `test2` identical, 56/56 ghosts, 13/13 suite cases, web module rebuilt (`?v=26`).
Decode notes added to `docs/kart_collision_decomp.md` ("Bike wheelie wobble", "Order of the karts' passes").

## `test3`: items (in progress)

Item use in the replayed race (race frames): P1 fake item box 671 to 787, fake item box 1538 to 3968, red shell 4215 to
4230, triple bananas 4448 to 4887, mushroom from 12740; P2 red shell 674 to 1860, mushroom 2703 to 2800. Kinoko has no
fake item box or red shell object, so `item <frame> <player> 20` lines (new: 20 empties the inventory) clear Kinoko's
inventory on the frames the game's became empty (787, 3968, 4230 for P1, 1860 for P2).

**Seeds.** The value at `RaceConfig +0xB94` (0xDEEF0BE5) is the right seed1: the game's first generator holds an older
state during loading and is reseeded with it at VI 3939, then makes **2 draws** at VI 3983 (still loading), then one
per frame from the intro on. Kinoko starts the per-frame draws at the same point but has no load-time draws, so at race
frame f the game is at f + 174 draws and Kinoko at f + 172. seed2 was recovered by stepping the second generator back
to a zero high word: 0x0100B425 (it only feeds the item boxes' model spin offline).

With `--rng1-skip 2` (temporary host option: two extra draws after loading) both first boxes match exactly. Decoded
from the game's generator states and the roulette block (KartItem +0x50: +0x58 spinning, +0x5C spin frame, +0x60
duration 184, +0x6C shown, +0x70 next, +0x74 decided): in a frame a box hit draws decide then shown, each spinning
roulette then draws its next item (list = items 0..18), and the frame's own advance comes last. Kinoko does the same.

**Source of the extra draws: the CPU AI layer** (found with a conditional breakpoint in Dolphin's debugger on the four
draw functions 0x80555578 / 0x805555CC / 0x80555628 / 0x805556A8, condition "r3 is RaceManager's first generator and LR
is not the once-per-frame draw at 0x80554CF8"). The game builds an AI object for every kart, human players included,
and 11 AI functions (0x8072FD38, 0x8073C644, 0x8073CD3C, 0x8073D060, 0x8073D59C, 0x8073DC78, 0x8073FAB4, 0x80740604,
0x807409B4, 0x80740B94, 0x80742FE0) call the helper 0x8073996C:

```c
f32 AiRandom(obj, f32 range) {        // 0x8073996C
    if (obj->+0x20 == 0) return RaceManager.random1.getF32(range);   // tail call 0x805556A8
    return range * 0.5f;                                              // 0x808A2714
}
```

The breakpoint stopped in 0x8073C644 while the karts were being created (call chain 0x8058FF20 KartObjectManager ->
0x8058E1B4 -> 0x80596000 -> 0x8072619C -> ... -> 0x8073C644), which accounts for the 2 load-time draws (one per
kart). Decompiled (Ghidra): the 11 callers are five route-follower variants (0x8073C644, 0x8073CD3C, 0x8073D060,
0x8073D59C, 0x8073DC78: a random sideways offset within the path width at an enemy route point, ENPT via
`CourseMap::getEnemyPoint`), CPU item use (0x8072FD38) and driving-style code (0x8073FAB4, 0x80740604, 0x807409B4,
0x80740B94, 0x80742FE0, the last also using a second helper `Enemy::AIManager::getRandU32` 0x80739944). The rare
mid-race +2 are most likely route recalculations: `Enemy::AI::handleBump` 0x807263CC (the "CPU AI notify" left out of
kart-kart collision), `onOutOfBounds` 0x807263B0, `forceRecalculation` 0x807263C4. The AI layer has 132 named functions
(`Enemy::AI`, `AIControlBase`, `AIManager`, airtime tracker, POW avoider, probability tables). Kinoko has no CPU AI, so it cannot make these
draws. Matching the real game's item rolls exactly needs at least the part of the AI that decides when these
functions run: a project of its own. Ruled out on the way: `RaceManager::Player::init` (draws once per player, but
from the second generator: `getU32(10)` at 0x805341C4, **not in Kinoko**, matters online where items use that
generator), `MiiObj` load (second generator), the course objects Kinoko builds, place changes.

**For Kinoko-only lockstep this does not matter**: every client runs the same code, so all make the same draws and
get the same items; only the mapping "seed -> item" differs from a real Wii. See "Server-controlled random numbers".

Also: one-frame +1 draws at 5335, 5875, 5882 fall in P1's triple-banana stretch (Kinoko's ported banana landing draw
should account for them once the earlier draws line up).

With every item now in Kinoko (item-objects session, web ?v=30) and no `item ... 20` clearing lines, `test3` with
`--rng1-skip 2` first differs at race frame 948: Kinoko's P1 is thrown up (extVel.y 30.06 against 0.057), apparently by
the fake item box it dropped at 787; the game's dump shows no item object of kind 3 at any point. Whether that is the
AI draws (931) or the fake item box port is not yet known.

## `test3` frame 948: items now leave the driver's hand (fixed 2026-11-02)

Checked against the `test3` dump (Fable). The box was **not** dropped at 787: P1 held the item button from 787 to 930,
so the fake item box trailed behind the kart (Kinoko and the game agree on it to the float from 806 to 933). At 931 the
button is released; both engines start the release (scale 0.5, held hit radius, drop velocity (7.527, 10.123, 2.272))
and keep following the kart for two frames. At frame 934 the game places the box at its drop anchor and runs the
drop state; Kinoko put it at the kart's own position (`ItemObj::calcRelease`, `frame == 0`), so it sank into the
floor, broke early, and its break sphere hit P1 at 948.

**Ported** (all uncommitted):

- `Render::DriverItemAnchor` (new, `source/game/render/DriverItemAnchor.*`): the game's anchor computation
  (`PlayerModel_init` 0x807C8758, node tree 0x807C7E7C, pose 0x807CAE8C, nw4r `ResAnmChr::GetAnmResult` 0x80055540
  with its keyframe decoders 0x80054270 / 0x800540F0 / 0x80053FB0 and `MTX34RotXYZFIdx` 0x80085940): the driver
  skeleton is posed with the driver's "throw_f" (slot 0x15) and "throw_b" (slot 0x17) animations at frame 4 and the
  `wrist_r1` node's translation (skeleton slot 13) is the anchor, once per pose. Same float operations as the game:
  fused multiply-adds, the hardware reciprocal estimate in the hermite step, the sine table, paired-single concat.
- `kinoko_host item-anchors <Race/Kart dir> <out>` (`source/host/DriverItemAnchorTool.cc`): runs that over the
  player's own kart archives and writes `Race/Kart/driverItemAnchors.bin` (504 entries, 14 KB, git-ignored); the
  web page loads it from `assets/common/driverItemAnchors.bin`. Team-colour archives (`*_red`, `*_blue`) are skipped.
- `KartBody::calcMatrix` (0x8056CE98, called from `KartObject::calc` where the game runs
  `PlayerSub_updateTransforms` 0x8059783C): the body matrix is the pose moved along its own up axis by the engine
  rumble, `rumbleHeight * SinFIdx(counter / 256) * scale.y`, the u16 counter advancing by the BSP's `rumbleSpeed`
  every frame (173 advances before race frame 0 in the game: one more than Kinoko's frames, so the first call advances
  twice). `KartParam.cc` read `rumbleSpeed` as a float; it is a u16.
- `KartModel::calcDriverMatrix` (+0x114 = body matrix x T(0, dispY, dispZ) from `kartDriverDispParam.bin`, scaled by
  the kart scale; King Boo uses the plain pose) and `KartModel::itemHandPosition` (0x807D171C): local
  `(0, y + d, z - d)` for a drop with `d = (1 - speedRatioCapped) * (itemRadius * itemScale + boundingRadius) /
  max(1, 5 * (1 + zAxis.y))`, `(0, y, z)` for a throw, times the kart scale (y at least 1), through the driver matrix.
- `ItemObj::calcRelease`: forward throws sit in the hand on release frames 0 and 1, drops are placed there on frame 2.

**Measured**: the box's position matches the game bit for bit from frame 934 on (`tools/kart_collision_diff.py items`:
2111 item-object frames compared to race frame 2800, 2023 bit-exact). `test3`'s first kart difference moved from
race frame 948 to **5335** (P1's triple-banana stretch, the banana landing draws). `test1` and `test2` unchanged
(no differences), 56/56 ghosts and 13/13 suite cases pass, web module `?v=32`.

**Still inexact**: the first ~15 frames of a *held* item (frames 787 to 805 of the fake item box, 1860 on for P2's
red shell): the game's trailing object starts about 72 (box) / 31 (shell) units lower while its scale grows from
0.0001 to 1, so the trail's hover height must scale with the object; it matches once the scale reaches 1 (805).
*Fixed in the `test4` round: the held item's scale vector includes its own scale (0x8079EDB4).*

## `test3` frame 5335: item-item collision and the banana spin (fixed 2026-11-02)

With the hand anchors in, `test3` next differed at 5335. P1 had dropped a second banana at 5316; at 5324 the game's
banana bounced off the first banana lying 95 units away (no course wall or object near: the collision triangles and
KMP objects were checked), Kinoko's flew through it ("items pass through each other"). The bounced banana landed at
5334, P1 ran over it at 5335 and the game spun P1 360 degrees at 10 degrees per frame from 5336; Kinoko entered
action 0 but never rotated and never ended it (its start was a stub).

**Ported** (all uncommitted):

- `ItemObj::calcItemCollision` (0x807A1C94), `calcItemPairFree` (0x807A0E28), `calcItemPair`, `itemPairResponse`
  (0x807A139C: a 15 x 15 table by item kind at 0x808A4DFC, 0 nothing / 1 bounce / 2 break; exploding bob-ombs and
  blue shells break anything not dropped unless weakened), `calcItemPairResponse` (0x807A18FC: dropped items that
  cannot survive hits vanish; 1 = wall-like bounce through the item's wall callback when moving into the other, then
  pushed out to the hit radius in x/z; 2 = detached from a trail, knocked away along the direction from the other
  item at speed 15, then broken) and `calcItemContact` (0x807A1680: the first contact of a frame kicks the item 13
  units in a random direction from the item generator, later contacts along the stored normal; the contact normal
  follows the wall normal). The box collision search before it (0x8079EFEC: items, objects, drivables).
- `KartAction::startAction0` (0x80567F68): action 0 is action 1 with rotation set 1 (one turn), sharing action 1's
  update (0x80568204) and end (0x8056837C); the game's table at 0x808B4D40 confirms it.

**Measured**: `test3` identical over 0 to 6713 (13,422 kart-frames), `test1` and `test2` unchanged, 56/56 ghosts,
13/13 suite cases, web module `?v=33`.

**Not ported**: item-vs-course-object collision (0x807A1ED8 with `ObjectDirector` 0x8082ADBC and the
`GeoHitTableItem(Obj).bin` tables, reaction 1 bounce / 2 break); no recording has exercised it yet.

## `test4`: a held item's scale (fixed 2026-11-03)

Recorded by the user (shell hits on both players, mushrooms, banana hits, maybe shell-on-shell) and checked on Opus.
Before the fix, Kinoko matched the game on every kart-frame from 0 to 17778, through 14 kart hits, the triple shells
and mushrooms, the triple mushroom and every item roll (the CPU-AI load draws are in Kinoko now). At 17779 the
game's P1, standing still, entered a hit action (status bit 32); Kinoko's one frame later. The cause was the banana P2
was dragging behind its kart (held from 17482): Kinoko's hung 4.65 units lower for the whole drag (game y 810.59,
Kinoko 805.95), so it reached P1's hitbox a frame later. 4.65 = 0.15 x 31: the banana's trail scale is 1.15 and its KCL
radius 31, and Kinoko used the kart's scale alone.

**Fixed**: `ItemObj::setScaleTrailVec` (0x8079EDB4) and the start of a trail (0x8079EA58, `ItemTrail` "use"): a held
item's scale vector is the kart's scale **times the item's own growing scale** (+0x68), and its KCL radius (+0xB4,
the hover height above the trail anchor) and hit radius (+0xB8) follow it. The game's hit radius in the dump shows it:
0.006 = 60 x 0.0001 when the item appears, 69 = 60 x 1.15 for a banana at full size. This also explains the "held item's
first ~15 frames" gap noted under `test3`: an item appears at scale 0.0001, so the game's hover height starts near zero,
not at the full KCL radius (72 for a fake item box, 31 for a shell).

**Measured**: `test4` identical over 0 to 18554 (36,850 kart-frames; nothing after the free-running stretch was
compared). Item objects up to 17790: 10,258 -> 12,179 of 14,574 object-frames bit-exact; up to 18554: 13,004 of 15,400.
`test1`, `test2` and `test3` (0 to 6713) unchanged (no differences), `test3` item objects 10,366 of 11,265
bit-exact, 56/56 ghosts, 13/13 suite cases, web module `?v=34`.

**Still inexact (items only; no kart was affected)**:
- The frame a shell or banana is thrown forward: in 10 throws the game reports the item exactly at the thrower's kart
  position, where Kinoko already has it in the driver's hand (2 to 3 units away); from the next frame on they agree bit
  for bit. In other throws the two agree. Deciding this needs the hand-position code (0x807D171C, render side), not
  decompiled yet.
- Green shells in flight drift by up to 0.026 units on some runs (float rounding), without changing any hit.
- The first frames of two held items still differ by 2 to 3 units (green shell 734 to 743, banana 2452 to 2488).

**Dolphin note**: the replay did not step at first because `Hotkeys.ini` (rewritten at 01:04 while `test4` was
recorded) no longer had a Frame Advance binding. It is now bound to F13 only (a key no keyboard has, so it cannot fire
while playing); the file before that change is `Hotkeys.ini.bak-before-test4`.

## `test5`: wooden boxes, dropped items and the respawn spot (fixed 2026-11-03)

Recorded by the user on DS Delfino Square (VS, items Basic). The Opus commit session ported what the boxes needed,
all committed: the kart-vs-object reaction filter by race mode (6c28b94), breakable wooden boxes outside Time Trials
with their random item drop and respawn (e24fca8), horizontal-only drag on dropped items (0d8a2c3), pickup of dropped
mushrooms and stars (8ad7bd9) and a reused item object keeping its old velocity (53d6255; the game's spawn reset never
clears it, so a mushroom from a box that reused the object of one that had fallen off the course flew the wrong way).
With those, the karts matched to race frame 9199 and every item object was bit-exact.

**Frame 9200**: P2 had fallen off the course and was put back on the track. Kinoko placed it exactly on respawn
point 3 (40010.3, 24726.7); the game 150 units to that point's left (39869.3, 24675.4), same height and heading.
The game's `MapdataJugemPoint` (0x805183A8) keeps the point's rotated -Z and -X axes, and `doRespawn` (0x80584334)
asks it for the player's spot (0x8051896C): outside Time Trials and ghost races the point is shifted by a per-player
table at 0x8088FA08, {left steps x 150, back steps x 300} = {-1,0}, {1,0}, {-3,0}, {3,0}, then the same with 1 and 2
steps back for players 5 to 12, so that players respawning together do not land on each other. Kinoko's
`calcRespawnStart` used the raw point.

**Ported** (uncommitted): `MapdataJugemPoint::respawnPos(playerIdx)` with `m_leftDir` / `m_backDir`, used by
`KartMove::calcRespawnStart`; and the rest of the game's respawn that touches the race: each respawn point links the
item route point nearest ahead of it inside a 15 degree cone (`linkNearestItemPoint`, 0x805184FC, run from
`CourseMap::init` as at 0x80512AE8), and the respawning kart's item point jumps there
(`KartItem::setRespawnItemPoint`, 0x807B99D4 from 0x80584334). Not ported, no effect on the race: the same link to
the nearest enemy route point (+0x28, for the CPU AI; Kinoko has no enemy route), the KCL probe 300 above the point
that picks the kart's light/shadow variant (0x80591924), the camera move (0x806AC400), Lakitu (0x8071E734), the
respawn sound (JGPT range / 100) and the CPU-AI `onOutOfBounds` (human karts make no AI draws).

**Measured**: `test5` identical over the whole recording (22,164 kart-frames), item objects 10,777 of 10,777
bit-exact; `test1` to `test4` unchanged (no differences), 56/56 ghosts, 13/13 suite cases, web module `?v=35`.

## Server-controlled random numbers (for lockstep online)

What draws from the race's two generators in Kinoko today: the first (RaceManager +0x04) feeds offline item rolls
(decide, roulette's shown items), the banana landing side, and course objects (Chain Chomp, cows, fire snakes, birds,
Basabasa); the second (+0x08) feeds the item boxes' model spin, and in the game also online item rolls and
`RaceManager::Player::init` (not in Kinoko). The game also draws from the first in its CPU AI layer (above), which
Kinoko does not have. All clients running Kinoko make the same draws, so they stay in step whatever the seeds are, as
long as every client gets the same seeds and the same inputs.

1. **Server sends the seeds** (works now): at race start the server picks seed1 / seed2 and sends them to every
   client (`kinoko_host versus --seed s1:s2`, web `kinoko_set_item_options(seed1, seed2, itemMode, humanMask)`).
   Cheap and already supported. Add a desync check: every N frames each client sends a hash of the two generator
   states (`System::Random::state()`, added this session) and of the karts' positions; the server compares them, so a
   client running a different build or course setup is caught at once instead of drifting silently.
2. **Server decides the items** (needs a small Kinoko hook): a client reports a box hit (frame, player); the server rolls
   the item with Kinoko's own odds code (place, item mode, cooldowns) and broadcasts {frame, player, item}; every client
   gives that item at the roulette's hand-over (about 184 frames later, plenty of time for the message). Clients
   cannot predict or rig their items, and item results no longer depend on draw counts. The roulette's own draws
   (decide, shown items) must still be made, or skipped, identically on every client, so the first generator stays in
   step for bananas and course objects.

Recommendation: 1 now (it is already built), with the generator/kart hash from the start; 2 later if cheating or mixed
client versions become a concern. Matching the real game's item rolls exactly (same seed -> same item as a Wii) would
additionally need the AI's draws.

## How to reproduce

Recordings, dumps and Kinoko outputs are outside the repo in `C:\Users\dwain\Documents\vs_verify\` (DTM movies only
hold inputs, but they stay out of the repo anyway).

Dolphin: `D:\Old stuff\dolphin-2412-x64` (portable), PAL `Mario Kart Wii.wbfs`. Config used (backups of the originals
are next to each file as `*.bak-before-vs-verify`): port 1 keyboard GC pad, port 2 PS4 pad (SDL), cheats on with only
"Race Count Modifier" enabled (forces the racer count to 2 at 0x8052F914, so a local VS race has no CPUs; it touches no
kart code), Frame Advance hotkey F (already set). CPU thread (dual core) off, as it was.

1. Record: Movie > Start Recording Input with no game running, boot the game, play, Movie > Stop, Export Recording.
2. Replay with the frame-locked logger (DolphinLuaServer-mkwii-lan, run from its folder):
   `Dolphin.exe -m <dtm> -e "D:\Old stuff\Mario Kart Wii.wbfs"`, then
   `build\Release\out.exe -s scripts\vs_verify_logger.lua -d <dump>.json`; end it with Ctrl+C or by creating
   `stop.flag` in that folder. About 8 race frames per second.
3. `python tools\kart_collision_diff.py inputs <dump>.json <in>.txt` (KPad state offset 0x28, now the default).
4. Characters, vehicles, course, engine class, item mode and seeds are in the dump (`config_player0/1`: vehicle at
   word 3, character at word 4; `config_settings`: course, engine class, game mode, ..., item mode at word 7, seeds at
   words 12 and 13); grid places are the racers' `place` at race frame 0.
5. `kinoko_host versus --course 8 --kart 0:1 --kart 7:1 --inputs <in>.txt --out <k>.csv --frames 8200 --cc 150
   --start 2,1 --human 0,1 --item-mode 3 --seed 0x96522BB6:0x5722` (the `test1` values; `test2`: `--kart 3:8
   --kart 1:24 --frames 15300 --seed 0xDB5B4DBB:0x9BB4`; `test4`: `--frames 18600 --item-mode 2 --seed
   0xA5852924:0x01005252 --items <k>_items.csv`; `test5`: `--course 23 --frames 11260 --item-mode 0 --seed
   0x71F4992B:0x01003249 --items <k>_items.csv`; `test3` takes `test3_in_noclear.txt` and `--frames 6900`), then
   `python tools\kart_collision_diff.py diff <dump>.json <k>.csv`.
6. To look at game fields the logger does not record, `scriptss_window_logger.lua` lets Dolphin run at full speed
   to `START_FRAME`, then steps and also dumps every racer's raw KartMove (0x2D0 bytes) up to `END_FRAME`, and leaves
   Dolphin paused there. `test2` window 11880 to 11960 took about 6 minutes instead of 35.

## Tooling fixes made on the way (none of these touch Kinoko's engine)

- `kinoko_host versus` CSV: five new columns `status0..status4`, Kinoko's status bits laid out as the game's five
  status words (KartState +0x04..+0x14), to compare with the logger's `status`. In both recordings the words are equal
  on every frame except bits 61 and 129, which the game always has set and Kinoko never sets (roles unknown, no effect
  seen).
- `test2` dump: 26 lost Frame Advance presses, one of them advanced two frames (race frame 5605 is missing). No pad
  changed on that frame, and the diff is clean past it.

- `tools/kart_collision_diff.py`: KPad state offset is 0x28 (checked: buttons u16 at +0x2C, stick floats at +0x30 /
  +0x34 in 1/7 steps, raw stick bytes at +0x38); floats compared as single precision (the game's floats arrive as
  doubles, Kinoko's as 9-digit decimals: comparing those as doubles flagged equal values); junk racer slots past the
  player count and menu entries without racers are skipped.
- DolphinLuaServer-mkwii-lan (outside the repo, originals kept as `*.bak`):
  - `send_key` sent keys by virtual-key code only; Dolphin reads the keyboard through DirectInput, which only sees scan
    codes, so Frame Advance never arrived. Now sent by scan code and held 30 ms.
  - `out.exe` calls the script once a second while Dolphin is paused (to resend a lost press), has `sleep_ms`, and
    stops on a `stop.flag` file as well as Ctrl+C.
  - New `scripts/vs_verify_logger.lua`: menus run free; in a race it pauses Dolphin, waits until the game state stops
    changing (the frame is finished), logs through `kart_collision_logger.lua`, and steps one frame. In `test1`: race
    frames 0 to 7908 without a gap, no frame changed during a read, 11 lost presses re-sent without skipping a frame.
    The external reads at full speed are unusable: they land mid-frame.

## Still to compare

- Items: a thrown item's first frame and two held items' first frames (`test4` section); item-vs-course-object
  collision; the stretches where Dolphin ran free (`test3` 6713 to 8431, `test4` 18555 to 20470) would need a
  re-record; nothing past frame 6713 of `test3` or 18554 of `test4` has been compared. `test5` is compared to
  its end.
- Two karts side by side at speed for a long time (only pushing at low speed so far).
- Status bit 131 (caps the speed limit at `0x8059144C()+0x84` in `calcAcceleration`): not in Kinoko, never set in
  either recording.
