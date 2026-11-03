#pragma once

#include "game/field/ObjectDirector.hh"
#include "game/field/obj/ObjectBreakable.hh"

namespace Kinoko::Field {

/// @brief A wooden box. In Time Trials it is an iron box that never breaks.
class ObjectWoodbox : public ObjectBreakable {
public:
    ObjectWoodbox(const System::MapdataGeoObj &params);
    ~ObjectWoodbox() override;

    void init() override;

    /// @addr{0x8077ED7C}
    [[nodiscard]] const char *getKclName() const override {
        return ObjectDirector::Instance()->isTimeTrial() ? "ironbox" : "woodbox";
    }

    void calcCollisionTransform() override;

protected:
    void respawn() override;
    void breakObject(u8 playerIdx, const EGG::Vector3f &dir) override;
    void calcFall() override;
    void breakByKart(Kart::KartObject *kartObj) override;
    void breakByKartUntimed(Kart::KartObject *kartObj) override;

private:
    f32 m_homeY;     ///< +0xC0: the height it stands at.
    f32 m_fallSpeed; ///< +0xC4
};

} // namespace Kinoko::Field
