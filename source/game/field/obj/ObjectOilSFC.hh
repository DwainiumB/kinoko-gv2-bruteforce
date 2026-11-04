#pragma once

#include "game/field/obj/ObjectCollidable.hh"

namespace Kinoko::Field {

class ObjectOilSFC final : public ObjectCollidable {
public:
    ObjectOilSFC(const System::MapdataGeoObj &params);
    ~ObjectOilSFC() override;

    /// @addr{0x806DDA54}
    /// @brief Items are not pushed out of the oil puddle.
    s32 onItemCollision(Item::ItemObj *item, s32 reactionOnItem, s32 /*reactionOnObj*/,
            EGG::Vector3f &hitDepth) override {
        if (item) {
            hitDepth.setZero();
        }
        return reactionOnItem;
    }

    Kart::Reaction onCollision(Kart::KartObject *kartObj, Kart::Reaction reactionOnKart,
            Kart::Reaction reactionOnObj, EGG::Vector3f &hitDepth) override;
};

} // namespace Kinoko::Field
