#pragma once

#include "game/item/ItemObj.hh"

namespace Kinoko::Item {

/// @brief A position on the item route: a point and the direction of travel (KartItem +0x44 and
/// the shells' +0x268 / +0x1DC, 0x10 bytes).
struct ItemRoutePos {
    u8 idx;            ///< +0x00 0xFF: none.
    bool forward;      ///< +0x01 Along the points' next links.
    EGG::Vector3f pos; ///< +0x04

    void set(u8 idx, bool forward);
};

/// @brief A cubic Bezier through the next item points (the shells' +0x1EC, 0x74 bytes; code at
/// 0x807B7D9C..0x807B8600).
struct ItemRouteSpline {
    std::array<EGG::Vector3f, 4> points;   ///< +0x00 The last, current, next and following point.
    std::array<EGG::Vector3f, 4> controls; ///< +0x30 Bezier control points (P1 .. P2).
    f32 length;                            ///< +0x60
    f32 invLength;                         ///< +0x64
    f32 speed;                             ///< +0x68
    f32 step;                              ///< +0x6C speed * invLength
    f32 t;                                 ///< +0x70

    void init(f32 speed, const std::array<EGG::Vector3f, 4> &pts);
    void calc();
    void setSpeed(f32 speed);
    [[nodiscard]] bool advance(const EGG::Vector3f &next);
    [[nodiscard]] EGG::Vector3f evalXZ() const;
    [[nodiscard]] EGG::Vector3f evalLerpY() const;
};

/// @brief Shared movement of the shells (the game's code at 0x807B3EFC..0x807B6FF0): they slide
/// along the floor at a set speed and bounce off walls a limited number of times.
/// @nosubgrouping
class ItemObjKoura : public ItemObj {
public:
    ItemObjKoura();
    ~ItemObjKoura() override;

protected:
    void initThrow(f32 speed, ItemTrail &trail, s32 bounces, bool forward, bool floats);
    void calcMove(f32 targetSpeed);
    void reflectOffWall(const EGG::Vector3f &nrm);
    void calcGravity();
    void calcGravityY();
    void freeFromVelocity();

    void initRoute(f32 speed, ItemTrail &trail, s32 routeFrames, s32 bounces, bool floats,
            u8 target, bool branchSearch);
    void calcRoute(f32 speed, f32 rate, u8 target, bool branchSearch);
    void calcRouteDirect(f32 speed, u8 target, bool branchSearch);
    [[nodiscard]] bool startRouteSpline();
    void calcRouteSpline(f32 speed, f32 rate, u8 target, bool branchSearch);
    void steerTowards(const EGG::Vector3f &dir);
    void chooseNextPoint(u8 target, bool branchSearch);

    f32 m_speed;              ///< +0x1A0
    EGG::Vector3f m_dir;      ///< +0x1A4
    EGG::Vector3f m_moveDir;  ///< +0x1B0
    EGG::Vector3f m_side;     ///< +0x1BC
    s32 m_bouncesLeft;        ///< +0x1C8 Breaks when it drops below 0.
    bool m_floats;            ///< +0x1CC Moves over water (other KCL mask, no wall push).
    bool m_limitBounces;      ///< +0x1CD
    bool m_reflects;          ///< +0x1CE
    bool m_touchedBoundary;   ///< +0x1CF
    s32 m_airTimer;           ///< +0x1D8 Frames it keeps flying after leaving the floor.
    ItemRoutePos m_routeNext; ///< +0x1DC
    ItemRouteSpline m_spline; ///< +0x1EC
    s32 m_routeTimer;         ///< +0x260 Frames of direct steering before the spline.
    f32 m_routeTimerInv;      ///< +0x264
    ItemRoutePos m_routeCur;  ///< +0x268
    bool m_routePassed;       ///< +0x278 Overshot the next point.
    f32 m_splineBlend;        ///< +0x27C
};

/// @brief The green shell (vtable 0x808D2430).
class ItemObjGreenShell : public ItemObjKoura {
public:
    ItemObjGreenShell();
    ~ItemObjGreenShell() override;

protected:
    [[nodiscard]] bool onRelease(ItemTrail &trail) override;
    [[nodiscard]] StateFunc initialState() const override;

private:
    void calcGreen();
};

} // namespace Kinoko::Item
