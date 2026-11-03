#pragma once

#include "game/item/ItemObj.hh"

namespace Kinoko::Item {

/// @brief Shared arc of the thrown and dropped items (the game's code at 0x807B7104..0x807B7B00:
/// banana, fake item box, bob-omb).
/// @nosubgrouping
class ItemObjThrowable : public ItemObj {
public:
    ItemObjThrowable();
    ~ItemObjThrowable() override;

protected:
    void initThrow(f32 forwardSpeed, f32 upSpeed, f32 backUpSpeed, ItemTrail &trail, u32 bounces,
            bool forward);
    void calcArc(f32 gravity, f32 drag, f32 bounce);
    void onArcWall(const EGG::Vector3f &nrm);

    f32 m_bouncesLeft; ///< +0x1A0 Floor bounces before it lands.
};

/// @brief The banana (vtable 0x808D1A38).
class ItemObjBanana : public ItemObjThrowable {
public:
    ItemObjBanana();
    ~ItemObjBanana() override;

protected:
    [[nodiscard]] bool onRelease(ItemTrail &trail) override;
    [[nodiscard]] s32 onBreak() override;
    [[nodiscard]] StateFunc initialState() const override;

private:
    void calcBanana();
    void calcBananaBreak();
};

} // namespace Kinoko::Item
