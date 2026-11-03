#pragma once

#include <Common.hh>

namespace Kinoko::Enemy {

/// @brief The CPU AI layer's random numbers.
/// @details The game's `Enemy::AIManager` draws them from RaceManager's first generator, so every
/// AI draw shifts the item rolls (and anything else on that generator). In time trials and ghost
/// races it returns fixed values instead and makes no draws. Kinoko has no AIManager object: only
/// this lookup is ported.
class AIManager {
public:
    [[nodiscard]] static f32 GetRandF32(f32 range);

private:
    [[nodiscard]] static bool IsRandomFixed();
};

} // namespace Kinoko::Enemy
