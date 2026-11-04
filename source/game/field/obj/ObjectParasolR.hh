#pragma once

#include "game/field/obj/ObjectCollidable.hh"

namespace Kinoko::Field {

/// @brief The parasols that open and close when a racer touches them.
/// @details Opening and closing (the animation, re-armed by the nearest racer within 600) is
/// visual. A harder hit (object reaction 4 or 6: shells, or a kart in a star, mega mushroom or
/// bullet bill) makes the parasol hop, which moves its collision.
class ObjectParasolR : public ObjectCollidable {
public:
    ObjectParasolR(const System::MapdataGeoObj &params);
    ~ObjectParasolR() override;

    void init() override;
    void calc() override;

    /// @addr{0x80779EF4}
    [[nodiscard]] u32 loadFlags() const override {
        return 1;
    }

    Kart::Reaction onCollision(Kart::KartObject *kartObj, Kart::Reaction reactionOnKart,
            Kart::Reaction reactionOnObj, EGG::Vector3f &hitDepth) override;
    s32 onItemCollision(Item::ItemObj *item, s32 reactionOnItem, s32 reactionOnObj,
            EGG::Vector3f &hitDepth) override;

private:
    void startHop();
    void calcBounce();

    bool m_hopping;      ///< +0xB4
    EGG::Vector3f m_vel; ///< +0xB8
};

} // namespace Kinoko::Field
