#pragma once

#include "game/kart/KartObjectProxy.hh"

namespace Kinoko::Kart {

/// @brief The bullet bill autopilot (the game's `KartKiller`, constructor 0x8059B658, at the
/// kart accessor's +0x60): it turns the kart towards the next item point every frame, flies over
/// raised points, and ends after a while depending on the rank.
/// @details The bullet's models, sounds, rumble and HUD are not ported, nor the online paths.
/// @nosubgrouping
class KartKiller : public KartObjectProxy {
public:
    KartKiller();
    ~KartKiller();

    void start(u8 point);
    void calc();
    void cancel();
    [[nodiscard]] bool calcTop();

    /// @beginGetters
    /// @brief Scales the bullet's speed (+0x2C, always 1.0).
    [[nodiscard]] f32 speedScale() const {
        return m_speedScale;
    }
    /// @endGetters

private:
    void calcAim();
    void calcPoint();
    void calcSteer();
    void calcLift();
    void calcEnd();
    [[nodiscard]] bool calcWall();
    [[nodiscard]] bool calcVoid();
    [[nodiscard]] bool inCorridor(const EGG::Vector3f &pos, bool checkSide) const;
    [[nodiscard]] EGG::Vector3f pointPos(bool raised, f32 *width) const;
    [[nodiscard]] EGG::Vector3f prevPointPos(bool raised, f32 *width) const;
    void setPoint(u8 point);

    u8 m_point;              ///< +0x10 The item point it heads for.
    u8 m_prevPoint;          ///< +0x11 0xFF: the first previous link of @ref m_point.
    s16 m_frame;             ///< +0x12
    s16 m_endRank;           ///< +0x14 Ends early once this rank is reached.
    s16 m_wallFrames;        ///< +0x16 Frames against walls (4 frames' grace).
    s16 m_wallGrace;         ///< +0x18
    f32 m_turnRate;          ///< +0x1C
    f32 m_speedScale;        ///< +0x2C
    bool m_ending;           ///< +0x30
    bool m_finished;         ///< +0x31
    bool m_raised;           ///< +0x3C Raised by the corridor test (not a point's setting).
    bool m_flying;           ///< +0x3D Aims 100 above the points, without gravity.
    bool m_voidCheck;        ///< +0x3E Rainbow Road: falling off ends it with a respawn.
    s32 m_noFlyTimer;        ///< +0x40
    u32 m_pointFlags;        ///< +0x44 From the point's settings (0x8059D2D4).
    EGG::Vector3f m_wallNrm; ///< +0x48
    s32 m_liftTimer;         ///< +0x54
    f32 m_lift;              ///< +0x58
    s32 m_sideTimer;         ///< +0x5C
    f32 m_side;              ///< +0x60
};

} // namespace Kinoko::Kart
