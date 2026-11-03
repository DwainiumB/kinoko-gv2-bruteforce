# Item objects: result

Session of 2026-10-31 (Opus 5.5, started from the VS items session). Nothing committed. Builds on the uncommitted
kart-kart collision, slipstream, VS grid and item-effect work (`KART_COLLISION_RESULT.md`, `ITEMS_RESULT.md`).

## Summary

| | status |
|---|---|
| Green shell | **Ported**: held behind the kart, thrown forward (9 wall bounces) or backward with the stick down (4), slides along the floor at 105, flies off ramps, breaks after 1500 frames, on its 10th bounce or when it hits a kart. |
| Banana | **Ported**: held behind, dropped behind or thrown forward with the stick up, arcs, lands, rests; spins a kart that touches it; breaks with its pop-and-shrink animation. |
| Item button (`KartItem::calc` 0x80797928) | **Ported in full** except the roulette, CPU and online parts: press uses, holding keeps the item behind the kart, release throws, stick up/down picks the direction, lockout masks. |
| Item vs kart (0x8057257C, 0x80799CAC, 0x807A14D4) | **Ported**: bounding-sphere test, then the item against the kart's convex hull (GJK); shell -> action 2, banana -> action 0, none in a mega. |
| Drops when hit | **Ported**: held items drop on spins / launches (0x80798B28); the inventory item drops on lightning and the other `loseItem` actions (countdown 0x807BC6E8 / 0x807BC610). A shell hit keeps the inventory item, as in the game. |
| Holders (spawn 0x80795E04, despawn 0x80795F68, update 0x80796470) | **Ported** (offline path), with the per-kind and the 30-item limits. |
| Red shell, triple items, fake item box, bob-omb, blue shell | **Not ported** (see below). Using them does nothing; the inventory keeps them. |
| Single-kart ghosts | 56/56 `samples/*.krkg` pairs sync to their full frame count; 13/13 `build/testCases.bin`. The two-kart bump race without items is byte-identical to the previous session's output. |
| Web module | Rebuilt, `?v=22`, new `kinoko_get_item_objects(float *out, int max)`. Not run in a browser with items. |
| Frame-exact check against Dolphin | **Not done**, as for the earlier work: no recording exists. Everything is checked against the decoded game code only. |

## Measurements (Kinoko only; Luigi Circuit, two Mario + Standard Kart M, `kinoko_host versus`)

Inputs: the previous session's `rear_base.txt` (kart 1 steers into kart 0, they touch at race frame 355) plus `item`
lines. New option: `--items <csv>` writes every item object per frame (kind, owner, held, flags, position, velocity,
scale, hit radius, box collision).

| scenario | result |
|---|---|
| Kart 1 gets a green shell at 300, presses at 310 | held behind the kart 310-313 (hit radius 70 = kart scale x 70, not yet collidable: scale below 0.8); the input file releases the button at 314: thrown, speed 126.9 at 315 (85 + the kart's displacement that frame), easing towards 105 by 1% per frame (106.1 at 600); scale 0.5 -> 2.1 (+0.03 per frame), hit radius 17 -> 71.4; wall bounce at 540. It misses kart 0 (aimed off by kart 1's steering, as the game's aim term does). |
| Kart 0 throws a green shell backward (stick down, released at 349) into kart 1 | kart 1 hit at 361: action 2 (launch) 361-461; the shell is knocked away (velocity 11.0 / -36.4) and breaks: out of box collision at once, despawned 20 frames later. |
| Kart 0 drops a banana at 320 | lands behind kart 0; kart 1 drives over it at 346: action 0 (spin). |
| Kart 1 holds a banana from 354, hit by the shell at 361 | action 2 starts the drop countdown: the banana leaves the kart at 362 (up 25 + kart), lands at ~390. |
| Kart 0 holds a banana in its inventory, kart 1 uses lightning at 300 | kart 0 shocked (action 10); the banana object spawns at 300 (scale 0.05), is released at 303, lands at ~330. |
| Kart 1 holds a banana in its inventory when the shell hits | the inventory item is kept (action 2 drops only held items, as in the game). |

## What was ported (files)

- `source/game/item/ItemObj.*`: the base object (`ItemObj` 0x8079D8BC): spawn reset 0x8079E5F4, calc 0x8079EFEC,
  kart test 0x807A14D4, kart hit 0x807A3790 / knock-away 0x807A6738, break 0x807A6560 / 0x807A6700, vanish
  0x807A6C14 / 0x807A6C90, release blend 0x807A25B0, dropped flight 0x807A7350, landing 0x807B6910 / 0x807A234C,
  wall slide 0x807A2270 / 0x807DE934, the property table 0x809C2F48 (all 15 kinds, hand-written values).
- `ItemObjKoura.*`: shell throw 0x807B5178, shell movement 0x807B54F4, green shell 0x807AEB98 / 0x807AEC64.
- `ItemObjBanana.*`: throwable arc 0x807B7104 / 0x807B7570, banana 0x807A3BE0 / 0x807A3E78 / 0x807A40F4 / 0x807A3C80.
- `ItemObjHolder.*`: the pool per kind (spawn, activate, despawn, landed list, update, eviction).
- `ItemTrail.*` (KartItem +0xB4): use 0x80791910, mode-1 held item (init 0x80792B08, calc 0x80792C68, position
  0x80792618, collisions 0x80791CC8), kart pose cache 0x80791E5C, throw direction 0x80794E88 / 0x80795030 /
  0x80794D1C, drops 0x8079231C tail, detach 0x80793164, clear 0x80794C44.
- `KartItem.*`, `ItemInventory.*`, `ItemDirector.*`: the button logic, the behaviour table 0x809C36A0, the drop
  countdown and spawn (0x807BC6E8, 0x807BC610, 0x807BC350, 0x807BC170), held-item drops 0x80798B28, director update
  order 0x80799850 and the kart hit query 0x80799CAC.
- Kart side: `KartCollide::calcItemCollision` 0x8057257C, called from `KartSub::calcPass1` after the object collision
  (skipped with status bits 82/83); the kart's box search includes items. `KartAction` spin / action 2 / action 5 and
  the bike wheelie bump drop held items. `ObjectCollisionKart::checkCollision(ObjectCollisionBase &)` (0x8081E25C).
- Field: `BoxColManager` item units (flag bit 1, `insertItem` 0x80786064, `getNextItem` 0x80785DF4),
  `CollisionDirector::checkSpherePartial` 0x8078F140. `KartMove::baseSpeed()`.
- Host: `versus --items <csv>`; web `kinoko_get_item_objects`.
- Notes: `docs/kart_collision_decomp.md`, section "Item objects (fourth pass)".

## Known differences from the game (approximations)

- **Release position.** For its first frames a released item is placed at the driver's hand from the driver model's
  matrix (0x807D171C, model +0x114 and per-model offsets). Kinoko has no driver model: the item starts at the kart's
  centre. This shifts where a shell or banana starts by up to the hand offset.
- **Random numbers** (banana spread, drop angle, landed knock-away) use Kinoko's single `RaceManager::random()`; the
  game picks one of two generators (RaceManager +0x8 / +0xC) by mode, and its seeds are not checked.
- **Float order.** Paired-single sums are written with Kinoko's `ps_dot` / `ps_squareMag` patterns; not every one was
  checked instruction by instruction.
- The holder's eviction sort (0x80796348) is not ported: the first active object is the one checked.
- Status bits 137-146 (in the item lockout mask) do not exist in Kinoko; the wheelie lift of held items uses three
  floats this object never sets in a race and is left at 0.

## Not ported (what is left)

- **Red shell** (0x807A9FF0..: homing on the item route, `ItemPathManager` 0x807B860C, target lock) and **blue shell**.
- **Triple items**: use modes 2 (banana chain, 0x807931DC / 0x8079356C) and 3 (orbiting shells, 0x8079455C /
  0x80794694); the inventory keeps them when used.
- **Fake item box** and **bob-omb** objects (FIB hit handler 0x8057325C, bob-omb explosion) and the mushroom / star
  objects dropped from inventories (those drops are simply lost).
- **Item vs item** collision (0x807A1C94, 0x807A0E28, 0x807A18FC): a shell passes through a banana. **Item vs course
  objects** (0x807A1ED8). Items riding **moving roads** (+0x134 handle; they rest where they land).
- Item boxes and the roulette, CPU item use, online item packets, battle, teams, the TC / POW / blooper objects, the
  bullet controller (as before).
- Visual-only parts: models, shadows, effects, sounds, the drawing-position blend, spin of the shell model.
- **Dolphin verification**: no recording. The logger and diff tooling from `KART_COLLISION_RESULT.md` still apply; a
  recording would need the item object list (ItemDirector +0x48 holders, ItemObj +0x44 position, +0x78 flags).

## Reverse-engineering setup

Shared notes folder `kart_collision_re/` scripts, plus this session's improved paired-single rewrite
(`pspatch2.py`, copied to the shared notes folder `item_objects_re/`): with it the item code decompiles with 2-3 truncated spots instead of
~110. A fresh Ghidra project with the rewrite takes ~2.5 minutes to import; 774 item functions decompile in ~6 minutes.
