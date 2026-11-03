#include "ItemObjFakeItemBox.hh"

#include "game/item/ItemTrail.hh"
#include "game/item/KartItem.hh"

namespace Kinoko::Item {

ItemObjFakeItemBox::ItemObjFakeItemBox() = default;

ItemObjFakeItemBox::~ItemObjFakeItemBox() = default;

/// @addr{0x807A7940}
/// @brief Dropped behind the kart (one floor bounce), or thrown forward with the stick held up
/// (three bounces).
bool ItemObjFakeItemBox::onRelease(ItemTrail &trail) {
    constexpr f32 FORWARD_SPEED = 70.0f;
    constexpr f32 UP_SPEED = 45.0f;
    constexpr f32 BACK_UP_SPEED = 10.0f;
    constexpr u32 DROP_BOUNCES = 1;
    constexpr u32 THROW_BOUNCES = 3;

    m_flags.setBit(eFlags::OwnerImmune15);
    bool forward = trail.kartItem()->stickUp();
    if (!forward) {
        initThrow(FORWARD_SPEED, UP_SPEED, BACK_UP_SPEED, trail, DROP_BOUNCES, false);
    } else {
        initThrow(FORWARD_SPEED, UP_SPEED, BACK_UP_SPEED, trail, THROW_BOUNCES, true);
        // The throw sound (0x807A2F18) is left out.
    }

    return forward;
}

/// @addr{0x807A79E0}
void ItemObjFakeItemBox::calcFakeItemBox() {
    constexpr f32 DROP_GRAVITY = 1.8f;
    constexpr f32 DROP_DRAG = 0.97f;
    constexpr f32 THROW_GRAVITY = 2.1f;
    constexpr f32 THROW_DRAG = 0.996f;
    constexpr f32 THROW_BOUNCE = 0.45f;

    if (m_flags.offBit(eFlags::FromKart)) {
        calcArc(DROP_GRAVITY, DROP_DRAG, 0.0f);
    } else {
        calcArc(THROW_GRAVITY, THROW_DRAG, THROW_BOUNCE);
    }

    if (m_frameFlags.onBit(eFrameFlags::Landed) &&
            m_frameFlags.offBit(eFrameFlags::Breaking, eFrameFlags::Vanishing)) {
        landOnFloor();
    }
}

ItemObj::StateFunc ItemObjFakeItemBox::initialState() const {
    return static_cast<StateFunc>(&ItemObjFakeItemBox::calcFakeItemBox);
}

} // namespace Kinoko::Item
