#include "AI.hh"

#include "game/enemy/AIManager.hh"

#include "game/system/CourseMap.hh"

namespace Kinoko::Enemy {

/// @addr{0x80726110}
/// @details The game's chain is `AI::init` -> AIEngine init (0x80733354, 0x80732508) -> AIControl
/// init -> AIPathHandler -> the route follower's start (0x8073C644), which places the kart's
/// target a random distance to the side of the path's centre. Only that draw is ported; the
/// offset itself steers a CPU and is not used by Kinoko.
void AI::Init() {
    // 0x8073C644: skipped when the course has no enemy (CPU route) paths
    if (System::CourseMap::Instance()->getEnemyPathCount() == 0) {
        return;
    }

    constexpr f32 MAX_SIDE_OFFSET = 100.0f; // 0x808CB048

    [[maybe_unused]] f32 sideOffset =
            static_cast<f32>(static_cast<u32>(AIManager::GetRandF32(2.0f * MAX_SIDE_OFFSET))) -
            MAX_SIDE_OFFSET;
}

} // namespace Kinoko::Enemy
