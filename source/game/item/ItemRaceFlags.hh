#pragma once

#include <Common.hh>

namespace Kinoko {

namespace System {

class Random;

} // namespace System

namespace Item {

/// @addr{0x809C38B8}
/// @brief What kind of race the item code runs in. The game fills these bytes from RaceConfig's
/// game mode before the item director is built (`RaceGlobals_init` 0x807BD1D0).
struct ItemRaceFlags {
    static void Init();

    /// @addr{0x807BD718}
    /// @brief The generator the item code draws from: RaceManager's second one (+0x08) online
    /// and in Time Trials, the first one (+0x04) in every other offline race.
    [[nodiscard]] static System::Random &Random();

    static u8 s_playerCount; ///< 0x809C38B8
    static bool s_online;    ///< 0x809C38B9 Online VS or battle.
    static bool s_versus;    ///< 0x809C38BA Offline VS.
    static bool s_battle;    ///< 0x809C38BB Offline or online battle.
    static bool s_timeTrial; ///< 0x809C38BC Time Trial and ghost race: no roulette.
    static bool s_teams;     ///< 0x809C38BD Team race (mode flag 2).
};

} // namespace Item

} // namespace Kinoko
