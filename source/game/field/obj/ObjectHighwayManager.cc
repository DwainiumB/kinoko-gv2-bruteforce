#include "ObjectHighwayManager.hh"

#include "game/system/RaceConfig.hh"

#include "game/field/ObjectDirector.hh"
#include "game/field/obj/ObjectCarTGE.hh"

namespace Kinoko::Field {

/// @addr{0x806D2908}
ObjectHighwayManager::ObjectHighwayManager()
    : ObjectCollidable("HighwayManager", EGG::Vector3f::zero, EGG::Vector3f::ez,
              EGG::Vector3f::unit) {
    size_t carCount = 0;
    auto *objDir = ObjectDirector::Instance();

    for (auto *const &obj : objDir->managedObjects()) {
        const char *objName = obj->getName();

        if ((strcmp(objName, "car_body") == 0) || (strcmp(objName, "kart_truck") == 0)) {
            ++carCount;
        }
    }

    m_cars = owning_span<ObjectCarTGE *>(carCount);
    size_t idx = 0;

    for (auto *&obj : objDir->managedObjects()) {
        const char *objName = obj->getName();

        if ((strcmp(objName, "car_body") == 0) || (strcmp(objName, "kart_truck") == 0)) {
            auto *carObj = reinterpret_cast<ObjectCarTGE *>(obj);
            m_cars[idx++] = carObj;
            carObj->setHighwayManager(this);
        }
    }
}

/// @addr{0x806D2FE8}
ObjectHighwayManager::~ObjectHighwayManager() = default;

/// @addr{0x806D332C}
void ObjectHighwayManager::init() {
    m_playerCount = System::RaceConfig::Instance()->raceScenario().playerCount;
    m_squashTimers.fill(SQUASH_MAX);
}

/// @addr{0x806D345C}
void ObjectHighwayManager::calc() {
    calcSquash();
}

/// @addr{0x806D50AC}
/// @details The manager's other per-frame work (bomb car blasts launching nearby cars, 0x806D52E0,
/// and the visual car effects) is not ported: Kinoko has no bomb cars.
void ObjectHighwayManager::calcSquash() {
    constexpr u32 SQUASH_INVULNERABILITY = 200;

    for (size_t i = 0; i < m_playerCount; ++i) {
        for (auto *&obj : m_cars) {
            if (obj->squashed(i) && m_squashTimers[i] >= SQUASH_INVULNERABILITY) {
                m_squashTimers[i] = 0;
            }
        }
    }

    for (auto *&obj : m_cars) {
        obj->reset();
    }

    for (size_t i = 0; i < m_playerCount; ++i) {
        m_squashTimers[i] = std::min<u32>(m_squashTimers[i] + 1, SQUASH_MAX);
    }
}

} // namespace Kinoko::Field
