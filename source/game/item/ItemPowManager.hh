#pragma once

#include <Common.hh>

#include <array>

namespace Kinoko::Item {

/// @brief The POW block (the game's manager at 0x809C3640, `PowManager`): it shakes three times
/// over 159 frames; every racer ahead of the user hops on the first two shakes and is spun by the
/// last one if on the ground (KartMove::calcPow).
/// @details The block's models, the screen shake, the rumble and the sounds are left out.
class ItemPowManager {
public:
    ItemPowManager();

    void init();
    void calc();
    void activate(u8 userIdx);

private:
    void shake(s32 stage);

    s32 m_timer;                    ///< +0x00
    u8 m_user;                      ///< +0x08 12: none.
    std::array<bool, 12> m_targets; ///< +0x09
};

} // namespace Kinoko::Item
