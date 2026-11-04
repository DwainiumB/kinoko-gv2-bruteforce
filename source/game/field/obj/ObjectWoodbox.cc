#include "ObjectWoodbox.hh"

#include "game/item/ItemObj.hh"

#include "game/field/CollisionDirector.hh"

#include "game/kart/KartObject.hh"
#include "game/kart/KartParam.hh"

namespace Kinoko::Field {

/// @addr{0x8077E5E4}
ObjectWoodbox::ObjectWoodbox(const System::MapdataGeoObj &params)
    : ObjectBreakable(params), m_homeY(0.0f), m_fallSpeed(0.0f) {}

/// @addr{0x8077E620}
ObjectWoodbox::~ObjectWoodbox() = default;

/// @addr{0x8077E678}
void ObjectWoodbox::init() {
    ObjectBreakable::init();
    m_homeY = pos().y;
    m_fallSpeed = 0.0f;
}

/// @addr{0x8077EBB8}
void ObjectWoodbox::calcCollisionTransform() {
    constexpr f32 HALF_SIZE = 100.0f;
    constexpr EGG::Vector3f POS_OFFSET = EGG::Vector3f(0.0f, HALF_SIZE, 0.0f);

    if (!m_collision) {
        return;
    }

    calcTransform();
    EGG::Matrix34f mat = transform();
    mat.setBase(3, pos() + POS_OFFSET);
    m_collision->transform(mat, scale(), getCollisionTranslation());
}

/// @addr{0x8077E750}
/// @brief The box comes back: it drops in from high above where it stood.
void ObjectWoodbox::respawn() {
    constexpr f32 DROP_HEIGHT = 5000.0f;

    ObjectBreakable::respawn();
    m_state = 3;
    setPos(EGG::Vector3f(pos().x, m_homeY + DROP_HEIGHT, pos().z));
    m_fallSpeed = 0.0f;
}

/// @addr{0x8077E704}
/// @details A box with setting 3 at 0 comes back after 300 frames, others stay broken.
void ObjectWoodbox::breakObject(u8 playerIdx, const EGG::Vector3f &dir) {
    constexpr s32 RESPAWN_FRAMES = 300;

    ObjectBreakable::breakObject(playerIdx, dir);

    if (m_mapObj->setting(3) == 0) {
        m_respawnTimer = RESPAWN_FRAMES;
    }
}

/// @addr{0x8077E7B0}
/// @brief Falls back into place and bounces on the course until it rests.
/// @details The landing sound is left out.
void ObjectWoodbox::calcFall() {
    constexpr f32 GRAVITY = 2.0f;
    constexpr f32 RADIUS = 100.0f;
    constexpr f32 BOUNCE = -0.1f;
    constexpr f32 REST_SPEED = 1.0f;
    constexpr KCLTypeMask MASK = 0x20E80FFF;

    m_fallSpeed -= GRAVITY;
    setPos(EGG::Vector3f(pos().x, pos().y + m_fallSpeed, pos().z));

    CollisionInfo info;
    info.bbox.setZero();
    EGG::Vector3f center = pos() + EGG::Vector3f(0.0f, RADIUS, 0.0f);
    if (!CollisionDirector::Instance()->checkSphereFull(RADIUS, center, EGG::Vector3f::inf, MASK,
                &info, nullptr, 0)) {
        return;
    }

    m_fallSpeed *= BOUNCE;
    addPos(info.tangentOff);

    if (EGG::Mathf::abs(m_fallSpeed) < REST_SPEED) {
        m_state = 1;
    }
}

/// @addr{0x8077E928}
/// @details The break effect (+0x100) and sound are left out.
void ObjectWoodbox::breakByKart(Kart::KartObject *kartObj) {
    breakObject(static_cast<u8>(kartObj->param()->playerIdx()), kartObj->velocity());
}

/// @addr{0x8077E9C0}
void ObjectWoodbox::breakByKartUntimed(Kart::KartObject *kartObj) {
    if (ObjectDirector::Instance()->isTimeTrial()) {
        return;
    }

    breakObject(static_cast<u8>(kartObj->param()->playerIdx()), kartObj->velocity());
}

/// @addr{0x8077EA6C}
/// @brief Broken by an item: the drop flies away from the item, credited to the item's owner.
/// @details The break effect (+0x100) and sound are left out.
void ObjectWoodbox::breakByItem(Item::ItemObj *item, const EGG::Vector3f &hitDepth) {
    breakObject(item->hitOwner(), -hitDepth);
}

/// @addr{0x8077EB08}
void ObjectWoodbox::breakByItemUntimed(Item::ItemObj *item, const EGG::Vector3f &hitDepth) {
    if (ObjectDirector::Instance()->isTimeTrial()) {
        return;
    }

    breakObject(item->hitOwner(), -hitDepth);
}

} // namespace Kinoko::Field
