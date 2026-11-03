# Task: make kart-to-kart collision 1:1 with Mario Kart Wii

Written 2026-10-30 by Fable for an Opus session. Write your findings and results to `KART_COLLISION_RESULT.md` in this folder
(real numbers, what matched, what did not, what is left). Commit nothing; leave the existing uncommitted edits (`KartMove.hh`,
`FrameState.cc`, `main.cc`, `web_bridge.cc`, `web/index.html`, the `_*.csv` files) alone.

## Goal

Kinoko (this repo, a C++ re-implementation of MKWii physics, frame-exact for single-kart ghosts) has a kart-to-kart collision that is a
**fork approximation**, not a port: `KartCollide::calcKartCollision()` in `source/game/kart/KartCollide.cc` (header comment in
`KartCollide.hh` explains it: overlapping BSP hitbox spheres, push along the line between them via `KartMove::applyForce`, split by
weight share, force tuned against one Dolphin recording). It is called from `KartSub::calcPass1` (`source/game/kart/KartSub.cc:195`)
right after `calcObjectCollision()`.

The user wants the real thing: the game's own kart-vs-kart function ported faithfully, verified frame-exact against Dolphin. Result:
two karts driven with identical inputs in Dolphin and in Kinoko produce identical positions, rotations, speeds and bump timers on
every frame, including the frames of contact.

## What is already known

- **The real function is named in the public symbol list.** em-eight/mkw, `config/RMCP01/module/symbols.txt` (PAL `StaticR.rel`):
  - `PlayerSub18_checkPlayerCollision = 0x8056F7F0`, size `0x1530` (about 1350 instructions). "PlayerSub18" is that list's name for the
    class Kinoko calls `KartCollide`; the other `PlayerSub18_*` symbols (`findCollision 0x80572C20`, `initHitboxes 0x805730D4`,
    `checkOob 0x80571634`, `activateOob 0x80573B00`, `updateRespawn 0x80573ED4`) are all already ported in `KartCollide.cc` with
    `@addr` comments, so you can line up field offsets and conventions from them.
  - Six unnamed functions immediately after it are **not** ported and are probably its callees: `0x80570D24 (0x84)`, `0x80570DA8 (0x48C)`,
    `0x80571234 (0x184)`, `0x80571484 (0xEC)`, `0x80571570 (0x84)`, `0x805715F4 (0x40)`. Also `0x8056F73C (0xB4)` just before it. Verify by
    looking at the call graph; do not assume.
  - `PlayerSub10_somethingWheelieBump = 0x80579FE4 (0x158)` in KartMove: bikes are knocked out of wheelies by bumps; probably reached from
    the collision code.
  - `PlayerSub18_checkItemCollision = 0x8057257C (0x618)` is the item-vs-kart equivalent; out of scope now, but note anything shared.
  - Copies of both symbol lists (main.dol and StaticR.rel) were downloaded to
    `C:\Users\dwain\AppData\Local\Temp\claude\C--Users-dwain-Documents-New-2-DolphinLuaServer-main\b50a2ff4-52f9-48c1-8469-5ef40a01b3d9\scratchpad\syms\`
    (`em8_symbols.txt`, `rel_symbols.txt`). If that folder is gone, re-download from
    `https://raw.githubusercontent.com/em-eight/mkw/master/config/RMCP01/module/symbols.txt` and `.../config/RMCP01/symbols.txt`.
- **Game files (PAL, RMCP01):** `C:\Users\dwain\mkw-tools\extracted\DATA\sys\main.dol` and
  `C:\Users\dwain\mkw-tools\extracted\DATA\files\rel\StaticR.rel`. The rel's `.text` really starts at `0x80510488` in the running game;
  em-eight's `splits.txt` says `0x805103B4`, which is `0xD4` too low. Kinoko's `@addr` comments are the trustworthy addresses.
  `C:\Users\dwain\MKWii\rel\StaticR.rel` is a different, non-PAL rel: do not use it.
- **Verified PAL struct layouts** (user's earlier RE, `C:\Users\dwain\Documents\New 2\DolphinLuaServer-mkwii-lan\ITEM_RE_HANDOFF.md`,
  read it): KartAccessor `+0x4 KartState, +0x8 body, +0x28 KartMove, +0x2C KartAction, +0x30 KartCollide`; KartCollide
  `+0x18 playerBumpTimer s16 (10 after a kart-kart hit), +0x2C surfaceFlags, +0x3C movement, +0x48 respawnTimer`; KartMove `+0x20 speed`;
  racer i = `KartObjectManager(0x809C18F8) -> +0x20 -> [4*i] -> +0x10 -> +0x0`.
- **Inputs the function likely uses, all already in Kinoko:** per-vehicle BSP hitbox spheres (`CollisionGroup` / `Hitbox`), `stats().weight`,
  `stats().bumpDeviationLevel` (`KartParam.hh:107`, used today only by `KartMove.cc:1660` for object bumps), `KartMove::m_bumpTimer`
  (`KartMove.hh:475`), the `SmallBump` / `BigBump` / `KnockbackBumpLoseItem` reactions in `KartCollide.cc`.
- **Decompilation tooling available on this machine:**
  - Ghidra: a working install was used for the CTGP-R work in `D:\ctgpr-re\ghidra` (projects in `proj/`, see how those were set up; the
    install itself came with the MKDS decomp toolchain, look under `C:\Users\dwain\Documents\MKDS-Decomp` tooling if the path is not
    obvious). Use the Gekko/Broadway language with paired singles; load `main.dol` and `StaticR.rel` at their real addresses and import
    the symbol lists so callees have names.
  - `C:\Users\dwain\Documents\New 2\DolphinLuaServer-mkwii-lan\scripts\ppcdis.py` (capstone, `python scripts\ppcdis.py 8056F7F0-80570D20`,
    not with `-I`) prints `.long` for paired-single opcodes, so it is only a fallback. Never name a script `dis.py`.
- **Verification tooling:** the user's Dolphin Lua server build `C:\Users\dwain\Documents\New 2\DolphinLuaServer-mkwii-lan`
  (`.\build\Release\out.exe -s scripts\<script>.lua -d <dump>.json`, dump written only on Ctrl+C; embedded Lua has no `math`/`string`/`bit`,
  no booleans in results; arrays come out as objects keyed "1".."n"). `scripts\kart_collision_logger.lua` already logs every racer's
  transform and speed per frame and was used to tune the current approximation. The sibling `DolphinLuaServer-main` must stay untouched.
  Kinoko's own input struct for player 1 in the game is at `0x8112368c` (from the LAN-sync project); player 2's is not yet known.

## Steps (estimates: your effort, run time is small)

1. **Decompile** `0x8056F7F0` and its callees in Ghidra (half a session to set up, 1 to 2 sessions to read). Produce annotated pseudo-C
   with every field named by role and the raw offset kept in a comment, in Kinoko's naming style. Record which other karts' fields it
   writes and in what order, how it iterates over karts, what it does with the bump timer, weight, `bumpDeviationLevel`, wheelies, and
   which `KartAction` it triggers. Save the pseudo-C to `docs/kart_collision_decomp.md` so the port can be checked against it.
2. **Port** it into `KartCollide` replacing `calcKartCollision` (1 to 2 sessions): same call site and position in `KartSub::calcPass1`
   as in the game (check the game's `calcPass1`, Kinoko `@addr{0x80596CFC}`, for where the `bl` to `0x8056F7F0` sits), same kart loop
   order, EGG vector math, `force25Bit`/`fma` where the game rounds (see how neighbouring ported functions do it). Keep every name human
   readable, `@addr` on each function. Build the native host first (`build-host`, ninja) and keep `STATUS.md`'s ghost test cases green
   (they are single-kart, so they must not change at all). Then rebuild the web module (emsdk env; `cd build; ninja kinoko_web`; copy
   `kinoko_web.js/.wasm` to `web/`; bump `?v=N` in `web/index.html`).
3. **Verify frame-exact against Dolphin** (about half a session plus iteration). Record a reproducible two-player split-screen VS race in
   Dolphin as a DTM movie (both controllers scripted or TAS-input driven; CPUs are not reproducible, so the second kart must be a player).
   Scenarios: side bump at matched speed, rear-end, heavy vs light vehicle, bike in a wheelie, two karts holding station side by side.
   Extend `kart_collision_logger.lua` to also log each racer's `playerBumpTimer` (+0x18 in KartCollide), speed and the per-frame inputs
   (read the game's KPad state or decode the DTM). Feed the same two input streams into a 2-kart Kinoko race (`kinoko_init_vs` with
   `kinoko_set_player_input`, or the native host) and diff position / rotation / speed / bump timer per frame for both karts. The first
   differing frame points at the port. Iterate until the diff is zero for all scenarios; report the remaining differences honestly
   if it is not.

## Rules

- Readability is non-negotiable: no `fn_1_xxxx`, `unk_`, `FUN_` names left in the port; name by role, keep the address in a comment.
- Nothing of Nintendo's goes into the repo (no game bytes, no asset files); pseudo-C notes are fine.
- Report real measurements, not hopes. If a step is blocked (Ghidra language missing, Dolphin not running), say so in the result file
  and do everything that does not depend on it.
