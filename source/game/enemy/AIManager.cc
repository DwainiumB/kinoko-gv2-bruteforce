#include "AIManager.hh"

#include "game/system/RaceConfig.hh"
#include "game/system/RaceManager.hh"

namespace Kinoko::Enemy {

/// @addr{0x8073996C}
f32 AIManager::GetRandF32(f32 range) {
    if (IsRandomFixed()) {
        return range * 0.5f;
    }

    return System::RaceManager::Instance()->random().getF32(range);
}

/// @brief The AIManager's +0x20 flag, set at construction (0x80738ED4).
bool AIManager::IsRandomFixed() {
    using GameMode = System::RaceConfig::Scenario::GameMode;

    GameMode mode = System::RaceConfig::Instance()->raceScenario().gameMode;
    return mode == GameMode::Time_Trial || mode == GameMode::Ghost_Race;
}

} // namespace Kinoko::Enemy
