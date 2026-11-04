#pragma once

#include "game/field/obj/ObjectDossun.hh"

namespace Kinoko::Field {

/// @brief A Thwomp that remains in one position and stomps downward.
class ObjectDossunNormal final : public ObjectDossun {
public:
    ObjectDossunNormal(const System::MapdataGeoObj &params);
    ~ObjectDossunNormal() override;

    void init() override;
    void calc() override;

    void startStill() override;

    void startBeforeFall();

    s32 onItemCollision(Item::ItemObj *item, s32 reactionOnItem, s32 reactionOnObj,
            EGG::Vector3f &hitDepth) override;
    void startSpin() override;

    /// @addr{0x807605EC}
    void calcSpinState() override {
        calcRiseWhileSpinning();
    }

    /// @addr{0x80760634}
    void calcSpin() override {
        calcSpinRotation(--m_spinFrames < 0);
    }

private:
    void calcInactive();

    s32 m_spinFrames = 0; ///< +0x124 Frames before the spin may stop.
};

} // namespace Kinoko::Field
