#pragma once

#include "game/field/obj/ObjectDossun.hh"

namespace Kinoko::Field {

/// @brief Thwomps that move along a rail and stomp.
class ObjectDossunSyuukai final : public ObjectDossun {
public:
    ObjectDossunSyuukai(const System::MapdataGeoObj &params);
    ~ObjectDossunSyuukai() override;

    void init() override;
    void calc() override;

    /// @addr{0x8076139C}
    void startStill() override {
        ObjectDossun::startStill();
        m_state = State::RotatingAfterStomp;
    }

    void startSpin() override;

    /// @addr{0x8075F520}
    void calcSpinState() override {
        calcRiseWhileSpinning();
        if (m_spinning) {
            calcSpin();
        }
    }

    /// @addr{0x8075F584}
    /// @brief The spin may stop in the last 30 frames of the stomp cycle.
    void calcSpin() override {
        constexpr s32 STOP_FRAMES = 30;
        calcSpinRotation(m_cycleTimer < STOP_FRAMES);
    }

private:
    enum class State {
        Moving = 0,
        RotatingBeforeStomp = 1,
        Stomping = 2,
        RotatingAfterStomp = 3,
    };

    void calcMoving();
    void calcRotating();

    State m_state;
    f32 m_initRotY;
    bool m_rotating;
};

} // namespace Kinoko::Field
