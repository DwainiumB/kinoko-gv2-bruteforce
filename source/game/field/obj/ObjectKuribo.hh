#pragma once

#include "game/field/StateManager.hh"
#include "game/field/obj/ObjectCollidable.hh"

namespace Kinoko::Field {

class ObjectKuribo : public ObjectCollidable, public StateManager {
public:
    ObjectKuribo(const System::MapdataGeoObj &params);
    ~ObjectKuribo() override;

    void init() override;
    void calc() override;

    /// @addr{0x806DD2C8}
    [[nodiscard]] u32 loadFlags() const override {
        return 3;
    }

    void loadAnims() override;

    Kart::Reaction onCollision(Kart::KartObject *kartObj, Kart::Reaction reactionOnKart,
            Kart::Reaction reactionOnObj, EGG::Vector3f &hitDepth) override;
    s32 onItemCollision(Item::ItemObj *item, s32 reactionOnItem, s32 reactionOnObj,
            EGG::Vector3f &hitDepth) override;

private:
    void calcKnockDir(const EGG::Vector3f &hitterVel);
    void squash(u8 playerIdx);
    void calcHitStages();
    void calcSquash();
    void calcHidden();
    void calcRegrow();

    void enterStateStub();
    void calcStateStub();
    void calcStateReroute();
    void calcStateWalk();

    void calcAnim();
    void calcRot();
    void checkSphereFull();

    f32 m_speedStep;
    f32 m_animStep;
    EGG::Vector3f m_origin;
    f32 m_maxAnimTimer;
    u32 m_frameCount;
    f32 m_currSpeed;
    EGG::Vector3f m_rot;
    EGG::Vector3f m_floorNrm;
    f32 m_animTimer;

    const s16 m_hiddenDuration;  ///< +0xD0 Setting 0: frames from the hit until it grows back.
    EGG::Vector3f m_railTangent; ///< +0xF8 The rail's direction at the start.
    EGG::Vector3f m_knockDir;    ///< +0xEC +-m_origin, away from the hitter's side of the rail.
    const bool m_dropsMushroom;  ///< +0x104 Outside Time Trials when the race has items.
    f32 m_squashScaleY;          ///< +0x12C
    f32 m_squashScaleXZ;         ///< +0x130
    u16 m_squashFrames;          ///< +0x134 How long the squash took.
    bool m_squashing;            ///< +0x136
    s32 m_squashTimer;           ///< +0x138
    bool m_hidden;               ///< +0x13C Blinking (visual) until m_hiddenDuration has passed.
    s32 m_hiddenTimer;           ///< +0x140
    bool m_regrowing;            ///< +0x144
    s32 m_regrowTimer;           ///< +0x148

    static constexpr std::array<StateManagerEntry, 4> STATE_ENTRIES = {{
            {StateEntry<ObjectKuribo, &ObjectKuribo::enterStateStub,
                    &ObjectKuribo::calcStateReroute>(0)},
            {StateEntry<ObjectKuribo, &ObjectKuribo::enterStateStub, &ObjectKuribo::calcStateWalk>(
                    1)},
            {StateEntry<ObjectKuribo, &ObjectKuribo::enterStateStub, &ObjectKuribo::calcStateStub>(
                    2)},
            {StateEntry<ObjectKuribo, &ObjectKuribo::enterStateStub, &ObjectKuribo::calcStateStub>(
                    3)},
    }};
};

} // namespace Kinoko::Field
