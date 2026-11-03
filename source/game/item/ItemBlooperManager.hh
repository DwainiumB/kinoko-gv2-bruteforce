#pragma once

#include <Common.hh>

#include <array>

namespace Kinoko::Item {

/// @brief The blooper (the game's manager at 0x809C3610, `GessoManager`): after its animation,
/// it inks the racers ahead of the user one after another.
/// @details The game keeps the manager busy until the blooper models of the local screens finish
/// their animations; Kinoko has no models, so it is free again once the last racer is inked.
class ItemBlooperManager {
public:
    ItemBlooperManager();

    void init();
    void calc();
    void activate(u8 userIdx);

private:
    void chooseTargets();

    u8 m_user;                     ///< +0x04 12: none.
    s32 m_timer;                   ///< +0x08 Counts up from 1 while active.
    s32 m_targetFrame;             ///< +0x0C The animation's length + 30.
    std::array<s32, 12> m_targets; ///< +0x10 Non-zero: still to be inked.
};

} // namespace Kinoko::Item
