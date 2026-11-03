# Item boxes and the item roulette: result

Session of 2026-10-31 (Opus 5.5, started from the VS items session). Nothing committed. Builds on the uncommitted
kart-kart collision, items and item-object work (`KART_COLLISION_RESULT.md`, `ITEMS_RESULT.md`,
`ITEM_OBJECTS_RESULT.md`). Notes: `docs/kart_collision_decomp.md`, section "Item boxes and the roulette (fifth pass)".

## Summary

| | status |
|---|---|
| Item box (`itembox`, 0x808285B0) | **Ported**: off the object blacklist; breaks when a kart drives through it, hidden and intangible for 150 frames (600 / 900 by KMP setting 5), tangible again from the 10th frame back. |
| Roulette (KartItem +0x54, 0x807BA37C) | **Ported**: decides the item on contact, spins 184 frames (45 for short boxes), slows down, can be stopped with the item button after frame 59, hands the item to `ItemInventory::setItem` 0x807BC940. |
| Odds (`ItemSlotData`, 0x807BB42C) | **Ported** for offline races: tables read from the game's ItemSlot.bin at run time (Common.szs, or the course's ItemSlotTable.slt), remapped by player count, item modes, cooldowns (lightning, blue shell, blooper, POW), mega / star / bullet / item-limit exclusions, room check with the mushroom fallback. |
| Place-based odds | From `RaceManager::Player::rank()` (the game's player +0x20). Player odds for `Local` players, CPU odds for `Cpu` ones (`--human` picks which). |
| Item points (0x807B8A9C, 0x807B8F30) | **Ported** with ITPH / ITPT parsing and point links (0x80517E88); every kart tracks its nearest item-route point. Nothing reads it yet (red shells are not ported). |
| Random numbers | Same generators as the game: see below. All item draws, including the banana / drop / knock-away ones of the item-object port, go through 0x807BD718. |
| Single-kart ghosts | 56/56 `samples/*.krkg` pairs sync to their full frame count (checked as `[n / n]`); 13/13 `build/testCases.bin`. |
| Earlier item-object scenarios | The 7 VS runs of the item-object session (b1, d1, d2, g1, g2, g3, l1): kart rows and item-object rows byte-identical. |
| Web module | Rebuilt, `?v=24`. New `kinoko_set_item_options(seed1, seed2, itemMode, humanMask)`, `kinoko_get_roulette(idx)`, `kinoko_get_player_item(idx)`. Same results as native in the browser. |
| Frame-exact check against Dolphin | **Not done**: no recording of a race through an item box exists. Checked against the decoded game code and the game's own table file only. |

## Random numbers (for lockstep clients)

- `RaceManager` +0x04 and +0x08 are two `Util::Random` seeded from `RaceConfig` scenario seed1 (+0xB94) and seed2
  (+0xB98) in the constructor 0x805327A0. `RaceConfig::Scenario::initRng` 0x8052F924 sets seed1 = 0x74A1B095 in Time
  Trials, missions and ghost races (seed2 from the clock); offline VS and GP take both from `OSGetTick`; online races
  keep the seeds the network gave them.
- The item code's generator (0x807BD718): **+0x04 in an offline race**, +0x08 online or in a Time Trial. +0x04 is also
  the one course objects use and the one advanced once per frame (end of `calcEnginesUnpaused`), so every client must
  run the same frames with the same objects; it does in lockstep.
- Kinoko has no clock: the host sets both seeds (`kinoko_host versus --seed <s1>[:<s2>]`, default `0x74A1B095:0`; web
  `kinoko_set_item_options`). Every client of a race must use the same pair.
- Draws per box: one in `decideItem` (on contact), then one per item shown by the roulette (about 20 over 184 frames).
  The item box constructor draws once from +0x08 (model spin) at load.

## Measurements (Kinoko; Luigi Circuit, two Mario on the same kart, both holding accelerate, `kinoko_host versus`)

Kart 0 has the player odds, kart 1 the CPU odds (default `--human 0`).

| scenario | result |
|---|---|
| Default seed | Both hit the first box row: kart 0 at race frame 588, kart 1 at 594. Roulettes stop at 772 / 778 (spin frame 185 > 184), items handed over at 801 / 807: kart 0 (1st) green shell, kart 1 (2nd) red shell. |
| Same seed run twice | Output byte-identical. |
| `--seed 1` | kart 0 banana at 785, kart 1 green shell at 807 (the earlier hand-over: the shown item already was the decided one). |
| `--seed 0x12345678:7` | banana / banana. |
| `--seed 0xDEADBEEF:0xCAFE` | triple bananas / bob-omb. |
| Item button at 620 and at 660 (kart 0) | 620 (spin frame 33) ignored; 660 (frame 73) stops it: item at 670 instead of 801, same item (decided on contact). |
| 300 seeds, kart 0 (1st, VS player table section 2, row 1) | green 31.7% (table 32.5%), banana 38.7% (37.5), mushroom 16.7% (17.5), triple bananas 13.0% (12.5). |
| 300 seeds, kart 1 (2nd of 2 = row 4, VS CPU table section 3) | green 18.0 (17.5), red 17.3 (17.5), banana 17.3 (17.5), fake box 8.3 (7.5), mushroom 13.3 (15.0), triple mushrooms 8.0 (7.5), bob-omb 4.3 (5.0), triple greens 7.0 (7.5); thunder cloud 0 (5.0): drawn, but its object is not ported, so no item (19 of 300 runs). Lightning and blue shell are on cooldown (1800 frames from the start). |
| Item points, kart 0 | point 12 at the grid, then 0 at race frame 393, 1 at 513, 2 at 591, 3 at 655, 4 at 845. Kart columns identical to the run before item points. |
| Browser (fresh wasm instance, same races) | Same items at the same frames (web steps = race frame + 171 intro frames): default seed green / red at steps 972 / 978; `0xDEADBEEF:0xCAFE` triple bananas / bob-omb. |

## What was ported (files)

- `source/game/field/obj/ObjectItembox.*`: constructor 0x808285B0, calc 0x80828860, kart hit 0x80828CB8.
  `ObjectId.hh`: item box off the blacklist; `ObjectDirector::createObject` builds it.
- `source/game/item/ItemSlotData.*`: create 0x807BA77C, load 0x807BAF48, section parse 0x807BA9D8, player-count remap
  0x807BAD20, `decideItem` 0x807BB42C, shown items 0x807BB8D0, cooldowns 0x807BB9EC and their resets.
- `source/game/item/ItemRoulette.*`: init 0x807B9F80, start 0x807B9FB0, calc 0x807BA37C, finish 0x807BA2D8, cancel
  0x807BA5D8, pending 0x807BA5D0.
- `source/game/item/ItemRaceFlags.*`: 0x809C38B8 flags (`RaceGlobals_init` 0x807BD1D0) and the generator choice
  0x807BD718.
- `KartItem`: human / remote flags (+0x19 / +0x1A), `startRoulette` 0x80798C38, `hasTripleItem` 0x80798DBC, roulette
  hand-over and press-to-stop in `calc` 0x80797928, cancel in `loseItem` / `clear`, item clear at race end, item-point
  tracker (+0x44: 0x807B99D4, 0x807B8A9C, 0x807B8F30). `useLightning` resets the lightning cooldown.
- `ItemDirector`: creates `ItemSlotData`, cooldowns first in `calc` 0x80799850, `hasRoomFor` 0x80799BE8, Time Trial
  starting mushrooms from the race flags. `ItemObjHolder`: `limit()` and the +0x0C room (limit - 1 + largest pickup,
  0x80790FB8). `ItemInventory::setItem(id, replaced)` (+0x29).
- `RaceConfig::Scenario`: game mode, item mode, seed1 / seed2, `initRng` 0x8052F924. `RaceManager`: second generator.
- `CourseMap`: ITPH / ITPT sections, item point links 0x80517E88, neighbour queries 0x805181F0 / 0x80518268 /
  0x805182CC / 0x80518344. New `map/MapdataItemPath.*`, `map/MapdataItemPoint.*`.
- Host: `versus --seed`, `--item-mode`, `--human`, VS game mode, output columns `roulette` (0 idle, 1 spinning,
  2 stopping), `rouletteItem` (shown item), `itemPoint`. `Host::Context` saves the new statics. Web: the exports above;
  a race without CPUs stays a Time Trial, ghosts are always Time Trials.

## Not ported (what is left)

- **Thunder cloud from a box**: the game spawns the cloud object here (0x8079A298); its object is not ported, so the
  item is lost (about 5% of 2nd-place CPU rolls in the measurement above).
- Flying (`f_itembox`), falling (`s_itembox`) and carried item boxes (Shy Guy, chain chomp); shells and other items
  breaking boxes (item-vs-object collision, see `ITEM_OBJECTS_RESULT.md`).
- Online and battle tables and roulette parts (network waits, roll-count limits, partner's triple items); tournament
  seed; team races.
- The CPU's record of the hit box (0x809C21D0 +0x68), rumble, sounds, effects, the box's grow-back and spin animation.
- Item-point resets at respawn (0x80584334) and by area type 4 (0x80798D0C).
- The roulette's pending item (+0x24) is ported, but the trail never sets it: Kinoko's held items never use the
  forced-release flag (+0x154).
- Item modes frantic / strategic are ported but were not run.

## Item object pool sizes (fixed after the first write-up)

`ItemObjHolder::init` sized each pool with the static property +0x08 (32 green shells, 48 bananas...). The game's pool
constructor (`ItemHolderItem_initObjs` 0x80795CCC, `lwz r30, 0xc(r6)`) allocates the runtime property +0x0C instead,
which 0x80790FB8 sets to limit - 1 + the largest pickup of that kind offline: 14 green shells, 10 red shells, 18
bananas, 14 mushrooms, 3 stars, 1 blue shell, 1 lightning, 6 fake boxes, 2 megas, 3 bob-ombs, 1 blooper, 1 POW, 2
golden mushrooms, 1 bullet, 1 thunder cloud. The pools now use that (`ItemObjHolder::room`). It only changes when the
oldest object is evicted in `spawn`; all 56 ghosts, the 13 cases, the 7 item-object races and the item box race give
the same output as before.

## Found while porting (not changed)
- `kinoko_web`'s init functions build a new scene without tearing down a running one: calling `kinoko_init_vs` on a
  module that already runs a race aborts with "Heap is locked" (seen when calling it by hand on the page's module,
  which runs a Time Trial after load). It predates this work; the browser checks above used a fresh module instance.
  Whether the page's own Start button can hit it was not checked.
