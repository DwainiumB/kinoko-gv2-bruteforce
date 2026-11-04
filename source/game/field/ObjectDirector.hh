#pragma once

#include "game/field/ObjectCollisionConvexHull.hh"
#include "game/field/ObjectCollisionPoint.hh"
#include "game/field/ObjectFlowTable.hh"
#include "game/field/ObjectHitTable.hh"
#include "game/field/obj/ObjectCollidable.hh"
#include "game/field/obj/ObjectNoImpl.hh"

#include "game/system/Random.hh"

#include <egg/core/Allocator.hh>

#include <vector>

namespace Kinoko {

namespace Host {

class Context;

} // namespace Host

namespace Item {

class ItemObj;

} // namespace Item

namespace Field {

class ObjectPsea;

class ObjectDirector : EGG::Disposer {
    friend class Host::Context;

public:
    void init();
    void calc();
    void addObject(ObjectCollidable *obj);
    void addObjectNoImpl(ObjectBase *obj);
    void addManagedObject(ObjectCollidable *obj);

    size_t checkKartObjectCollision(Kart::KartObject *kartObj,
            ObjectCollisionConvexHull *convexHull);
    size_t checkItemObjectCollision(f32 radius, Item::ItemObj *item, const EGG::Vector3f &pos);
    [[nodiscard]] EGG::Vector3f collidingObjectTranslation(size_t idx) const;

    [[nodiscard]] const ObjectFlowTable &flowTable() const {
        return m_flowTable;
    }

    [[nodiscard]] const ObjectHitTable &hitTableKart() const {
        return m_hitTableKart;
    }

    [[nodiscard]] const ObjectCollidable *collidingObject(size_t idx) const {
        ASSERT(idx < m_collidingObjects.size());
        return m_collidingObjects[idx];
    }

    [[nodiscard]] Kart::Reaction reaction(size_t idx) const {
        ASSERT(idx < m_reactions.size());
        return m_reactions[idx];
    }

    /// @brief What the hit does to the item (director +0x48, written by the item search).
    [[nodiscard]] s32 itemReaction(size_t idx) const {
        ASSERT(idx < m_itemReactions.size());
        return m_itemReactions[idx];
    }

    [[nodiscard]] const EGG::Vector3f &hitDepth(size_t idx) const {
        ASSERT(idx < m_hitDepths.size());
        return m_hitDepths[idx];
    }

    [[nodiscard]] fixed_vector<ObjectCollidable *> &managedObjects() {
        return m_managedObjects;
    }

    [[nodiscard]] const fixed_vector<ObjectCollidable *> &managedObjects() const {
        return m_managedObjects;
    }

    [[nodiscard]] const fixed_vector<ObjectBase *> &objects() const {
        return m_objects;
    }

    void setPsea(ObjectPsea *psea) {
        m_psea = psea;
    }

    [[nodiscard]] ObjectPsea *psea() const {
        return m_psea;
    }

    /// @brief Online race: game mode 7 or higher (offset 0x54).
    [[nodiscard]] bool isOnline() const {
        return m_online;
    }

    /// @brief Time Trial or ghost race (offset 0x55). Several objects behave differently then.
    [[nodiscard]] bool isTimeTrial() const {
        return m_timeTrial;
    }

    [[nodiscard]] System::Random &random() const;
    [[nodiscard]] f32 distAboveRisingWater(f32 offset) const;
    [[nodiscard]] f32 risingWaterKillPlaneHeight() const;

    ///< @addr{0x808C70E8}
    [[nodiscard]] static f32 WanwanMaxPitch() {
        return s_wanwanMaxPitch;
    }

    static ObjectDirector *CreateInstance();
    static void DestroyInstance();

    [[nodiscard]] static ObjectDirector *Instance() {
        return s_instance;
    }

private:
    EGG_NEW_DELETE_FRIEND

    ObjectDirector();
    ~ObjectDirector() override;

    void createObjects();
    [[nodiscard]] ObjectBase *createObject(const System::MapdataGeoObj &params);

    ObjectFlowTable m_flowTable;
    ObjectHitTable m_hitTableItem;       ///< +0x08 What a course object does to an item.
    ObjectHitTable m_hitTableItemObject; ///< +0x0C What an item does to a course object.
    ObjectHitTable m_hitTableKart;
    ObjectHitTable m_hitTableKartObject;

    fixed_vector<ObjectBase *> m_objects;          ///< All objects live here
    fixed_vector<ObjectBase *> m_calcObjects;      ///< Objects needing calc() live here too.
    fixed_vector<ObjectBase *> m_collisionObjects; ///< Objects having collision live here too

    static constexpr size_t MAX_UNIT_COUNT = 0x100;

    std::array<ObjectCollidable *, MAX_UNIT_COUNT>
            m_collidingObjects; ///< Objects we are currently colliding with
    std::array<EGG::Vector3f, MAX_UNIT_COUNT> m_hitDepths;
    std::array<Kart::Reaction, MAX_UNIT_COUNT> m_reactions;
    /// The item search's reactions. The game writes them into the same array as the kart ones
    /// (+0x48); both are read right after their search.
    std::array<s32, MAX_UNIT_COUNT> m_itemReactions;
    ObjectCollisionPoint m_itemCollision; ///< +0x134 The searched item as a point and radius.
    ObjectPsea *m_psea;
    fixed_vector<ObjectCollidable *> m_managedObjects;
    bool m_online;
    bool m_timeTrial;

    static f32 s_wanwanMaxPitch; ///< @addr{0x808C70E8}

    static constexpr size_t MAX_MANAGED_OBJECTS = 400; ///< Maximum number of managed objects

    static ObjectDirector *s_instance;
};

} // namespace Field

} // namespace Kinoko
