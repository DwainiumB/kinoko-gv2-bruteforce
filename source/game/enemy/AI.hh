#pragma once

#include <Common.hh>

namespace Kinoko::Enemy {

/// @brief The part of the game's per-kart CPU AI (`Enemy::AI`) that touches the race's random
/// numbers when no CPU is driving.
/// @details The game builds an AI for every kart, human players included. For a human kart it
/// never drives, but its route follower still picks a random sideways offset when the kart is
/// created: one draw from RaceManager's first generator per kart, before the race starts. Later
/// draws only happen while a CPU drives the kart (respawns, bumps, route choices, item use, and
/// a human kart after it finishes), which Kinoko does not have, so they are not ported.
class AI {
public:
    static void Init();
};

} // namespace Kinoko::Enemy
