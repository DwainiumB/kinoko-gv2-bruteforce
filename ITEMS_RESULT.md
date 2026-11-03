# VS items: result

Session of 2026-10-31 (Opus, forked from the kart-kart collision session). Nothing committed. Builds on the
uncommitted kart-kart collision, slipstream, engine class and VS start-grid work (`KART_COLLISION_RESULT.md`).

## Summary

| | status |
|---|---|
| Item effects on karts | **Ported:** star, mega mushroom, lightning (with a live race rank), golden mushroom, blooper ink (state), thunder cloud (state), the kart-kart star/mega/bullet outcomes now reachable, KartAction actions 6, 10, 13 and 17. |
| Using items | `KartItem` now dispatches on the held item: mushroom, triple mushroom, golden, star, mega, lightning. |
| Single-kart ghosts | Unchanged: all 56 `samples/*.krkg` pairs sync to their full frame count, 13/13 `build/testCases.bin`. The plain two-kart bump from the collision work is bit-identical (frame 355: 25.874815 / 62.1951866). |
| Web module | Rebuilt, `?v=21`, new `kinoko_set_player_item(idx, itemId)`. |
| Frame-exact check against Dolphin | **Not done**, same as the collision work: no two-player recording exists. Everything below is checked against the decoded game code only. |

## What was ported (game addresses)

**KartMove**
- `activateStar` 0x80580268: refused while in a bullet, an action or the unidentified states 72/82/83; sets bit 63
  for 450 frames, offroad invincibility at least 450 frames, clears ink and an ongoing crush. Timer
  `calcStar` 0x805803F0, after `calcMega` and before `calcShock` as in `KartMove::calc` 0x805788DC.
- `activateMega` 0x80580B14 / `calcMega` 0x80580DC0 / `deactivateMega` 0x80580CDC: bit 79 for 450 frames, a mega scale
  that ramps +0.02 per frame up to the stats' `megaScale` (and -0.1 per frame back to 1), the shrink-back animation
  starting 26 frames before the end, ends a shock and a crush. `calcScale` now multiplies the total scale by it.
  The kart's box-collision sphere is resized by `setObjectCollisionScale` 0x80598338.
- `KartScale` types 2 and 3 (`kinoko_scale_up` / `kinoko_scale_down` from `driver.brres`, loaded beside the thunder
  ones, game loader 0x8056AB6C): the mega grows and shrinks the kart. Kinoko panicked on these before.
- `applyLightningEffect` 0x80580778 (Kinoko's `applyShrink` was a simplified copy of it, now a wrapper): the game's
  full guard (respawn, cannon, star, bullet states), a mega only ends the mega, else action 10 / 15 / 17 (lightning /
  shrinking object / POW), the held item lost, shock for the given time. `applyLightning` 0x80580438 picks the time
  from the rank: `{690, 645, 600, 555, 510, 450, 390, 330, 270, 210, 150, 90}[rank + 11 - players] + 72`.
- `applyInk` 0x80581A58, `calcInk` 0x80581B1C (timer only), `clearInk` 0x80581C70; `activateThunderCloud` /
  `deactivateThunderCloud` 0x80581A28 / 0x80581A40.
- Speed: acceleration 3.0 in a star, mega or thunder cloud (`calcVehicleSpeed` 0x8057AB68, before the slipstream's
  0.7); boost speed limit at least 95 (mega, thunder cloud) / 105 (star) / 115 (slipstream) (`calcAcceleration`
  0x8057B9BC).

**KartAction**
- `start` 0x805675DC now refuses as the game does: in a star, a bullet, a cannon, the respawn states, the unidentified
  states 40/72/82/83/89, and in a mega unless the caller can hit megas (a star or a bullet can; objects can't).
- Action 6 (hit by a bullet) start 0x80569024 (action 4's launch, variant 2) with action 4's calc and end; actions 10
  and 17 (lightning, POW) start 0x8056804C = `startRotation(2)` with action 1's calc and end; action 13 (squashed by a
  mega) start 0x80569818: 20-frame action, 500-frame crush, press calc. The press actions now set bit 81 and the
  crush end clears it, as in the game.
- Items lost when hit, and at respawn, now use the hit kart's own item holder: Kinoko used `kartItem(0)` everywhere.

**Items**
- `ItemId` has every game id; `ItemInventory` takes its use count per item (triple items 3, else 1) and has the
  golden mushroom's timer (`calc` 0x807BC6E8, `startTimer` 0x807BCAB0, `setTimerUse` 0x807BCAD0). The counts and the
  timed flag are the game's boot-time behaviour table values (0x809C36A0), written out by hand.
- `KartItem`: `useItem` dispatch, `useGolden` 0x807A9F64, `useStar` 0x807B706C, `useMega` 0x807A9E50,
  `useLightning` 0x807B7B7C, `hitByLightning` 0x80798728, `loseItem` 0x80798A30 (inventory part only).
- `ItemDirector::activateLightning` 0x807B7C20. `ItemDirector::init` gives the starting triple mushrooms only to a
  single racer (the game uses a time-trial flag at 0x809C38BC; Kinoko has no game modes).

**RaceManager**: live rank, `calcRanks` 0x805336D8 (insertion sort from last frame's order by race completion, finished
racers scored `0.01 * index + 6000099 - finish time in ms`), starting from the grid place.

**Host**: `kinoko_host versus` input line `item <race frame> <player> <item id>`; output columns `item`, `itemCount`,
`effects` (1 star, 2 mega, 4 shocked, 8 inked, 16 crushed, 32 thunder cloud), `rank`, `action`.

## Measurements (Kinoko only; Luigi Circuit, two Mario + Standard Kart M)

| scenario | result |
|---|---|
| Star used at race frame 320 | star from 320 to 770 (450 frames); top speed 105.000 (79.770 without) |
| Mega used at 300 | mega from 300 to 750; top speed 95.000 |
| Mega kart rear-ends a coasting kart (use at 350 / 357) | the other kart: action 13 from 361 / 363 for 21 frames, crushed, speed 0.0, no ordinary bump |
| Star kart rear-ends it (use at 350 / 357) | the other kart: action 3 (launch) from 361 / 364 for 100 frames |
| Kart 1 (2nd of 2) uses lightning at 300 | kart 0 (1st): shocked 300 to 522 = 222 frames (150 + 72), action 10 for 72 frames; kart 1 not hit; ranks swap at 328 when kart 1 passes |
| Golden used at 300, pressed every 30 frames | item held until 749 (449 frames); speed 115.000 (mushroom boost cap) on the boosts |
| Same star test in the browser (wasm) | top speed 105.00 |

## Not ported (what is left)

- **Item objects**: shells, bananas, fake item boxes, bob-ombs, blue shell, POW, blooper, thunder cloud. Using one of
  these does nothing yet; the thunder cloud's carrying and zap and the blooper's inking of racers ahead live in their
  objects. The kart effects they cause (`applyInk`, `activateThunderCloud`, `applyLightningEffect` with POW, the
  actions) are ported and ready for them.
- **Bullet bill**: `KartMove::activateBullet` 0x805858AC and the bullet controller (`KartKiller`, 0x8059B658...) that
  drives the kart along the route. Bit 91 is checked everywhere but never set.
- **Item boxes and the roulette** (`ItemRoulette_update` 0x807BA37C, item points 0x807B8A9C), rank-based item odds,
  dropped and trailing items (the inventory's drop countdown), the full `KartItem::calc` (0x80797928) button logic:
  Kinoko keeps its simplified press-to-use.
- **CPU item use** (AI), battle items and balloons, teams, online item packets.
- Objects that react to a star or mega kart (cars bouncing off, objects broken): object-side, not checked.
- Visual-only parts: star flashing, ink splat on screen, model and sound effects, item HUD.
- The second kart sphere the mega resize also scales (accessor +0x50) has no Kinoko counterpart.

## Files changed (uncommitted)

`source/game/item/{ItemId.hh, ItemInventory.*, KartItem.*, ItemDirector.*}`, `source/game/kart/{KartMove.*,
KartAction.*, KartCollide.cc, KartScale.cc, KartObjectManager.*, Status.hh}`, `source/game/system/RaceManager.*`,
`source/host/{KVersusSystem.*, web_bridge.cc}`, `docs/kart_collision_decomp.md` (items section), `web/kinoko_web.*`,
`web/index.html` (`?v=21`).
