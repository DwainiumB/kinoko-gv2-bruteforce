#pragma once

#include "game/item/ItemObjBanana.hh"

namespace Kinoko::Item {

/// @brief The bob-omb (vtable 0x808D1BE0): thrown in an arc (or dropped behind), it lies on the
/// course until its fuse runs out or a racer comes close, then explodes. Its item state is a
/// small state machine of its own (+0x1A4, table 0x808D1B18): 0 flying, 1 on the floor with the
/// fuse burning, 2 exploding.
/// @details Model, effect and sound members are not ported, nor the battle team checks.
/// @nosubgrouping
class ItemObjBobOmb : public ItemObjThrowable {
public:
    ItemObjBobOmb();
    ~ItemObjBobOmb() override;

    /// @beginGetters
    /// @brief The explosion is past its launching part (+0x1D8): it only spins racers now.
    [[nodiscard]] bool explosionWeakened() const {
        return m_weakened;
    }

    /// @brief In its explosion (sub-state 2): breaks items it touches while not weakened.
    [[nodiscard]] bool isExploding() const {
        return m_subState == SubState::Explode;
    }
    /// @endGetters

protected:
    void onSpawn() override;
    [[nodiscard]] bool onRelease(ItemTrail &trail) override;
    [[nodiscard]] s32 onBreak() override;
    void onDrop() override;
    [[nodiscard]] StateFunc initialState() const override;

private:
    enum class SubState {
        Flying = 0,
        Fuse = 1,
        Explode = 2,
    };

    void calcBobOmb();
    void setNextSubState(SubState state);
    void calcFlying();
    void calcFuse();
    void enterExplode();
    void calcExplode();
    void checkKartNear(u8 playerIdx);

    SubState m_subState; ///< +0x1A8
    s32 m_nextSubState;  ///< +0x1AC -1: none.
    s32 m_subFrame;      ///< +0x1B0
    f32 m_bounce;        ///< +0x1D0 Floor bounce of a dropped bob-omb.
    bool m_weakened;     ///< +0x1D8
    s32 m_fuse;          ///< +0x1DC Explodes when it drops below 0.
    u8 m_nearestKart;    ///< +0x1E4 12: none.
    f32 m_nearestDistSq; ///< +0x1E8
    s32 m_noTrigger;     ///< +0x1EC Frames the racers' approach cannot shorten the fuse.
};

} // namespace Kinoko::Item
