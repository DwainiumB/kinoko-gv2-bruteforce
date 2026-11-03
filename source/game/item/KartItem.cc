#include "KartItem.hh"

#include "game/item/ItemDirector.hh"
#include "game/item/ItemRaceFlags.hh"
#include "game/item/ItemSlotData.hh"

#include "game/kart/KartMove.hh"
#include "game/kart/KartObject.hh"
#include "game/kart/KartObjectManager.hh"
#include "game/kart/KartState.hh"

#include "game/system/CourseMap.hh"
#include "game/system/RaceConfig.hh"
#include "game/system/RaceManager.hh"

#include <limits>

namespace Kinoko::Item {

/// @addr{0x8079754C}
KartItem::KartItem()
    : m_playerIdx(0), m_isHuman(false), m_isRemote(false), m_throwPitch(0.0f),
      m_smoothedStickX(0.0f) {
    m_flags.makeAllZero();
}

/// @addr{0x8079951C}
KartItem::~KartItem() = default;

/// @addr{0x807976E0}
void KartItem::init(size_t playerIdx) {
    using PlayerType = System::RaceConfig::Player::Type;

    m_playerIdx = playerIdx;
    // 0x807BD5BC: CPUs (and the online and empty slots) get the CPU odds.
    PlayerType type = System::RaceConfig::Instance()->raceScenario().players[playerIdx].type;
    m_isHuman = type != PlayerType::Cpu && type != PlayerType::None;
    m_isRemote = false;
    apply(playerIdx);
    m_flags.makeAllZero();
    m_prevPos = pos();
    m_posDelta.setZero();
    m_throwPitch = 0.0f;
    m_smoothedStickX = 0.0f;
    m_roulette.init(this);
    m_inventory.init(this);
    m_trail.init(this, playerIdx);

    bool hasItemRoute = System::CourseMap::Instance()->getItemPathCount() != 0;
    setItemPoint(hasItemRoute ? 0 : System::MapdataItemPoint::NONE, true);
}

const Kart::KartObject *KartItem::kartObject() const {
    return Kart::KartObjectManager::Instance()->object(m_playerIdx);
}

f32 KartItem::speedRatio() const {
    return move()->speedRatioCapped();
}

/// @brief Calculates item activation based on the controller input state
/// @addr{0x80797928}
/// @details Pressing the button uses the inventory's item (an item with an object is then held
/// behind the kart); releasing it throws a held item. The stick held up or down at that moment
/// picks the direction. A spinning roulette hands its item to the inventory when it stops. CPU
/// item use and the online parts are not ported.
void KartItem::calc() {
    constexpr f32 STICK_RATE = 1.0f / 15.0f;
    constexpr f32 MAX_PITCH = 0.85f;
    constexpr f32 PITCH_SCALE = 0.9f;
    constexpr f32 PITCH_RATE = 0.05f;
    constexpr f32 STICK_ON = 0.6f;
    constexpr f32 STICK_OFF = 0.1f;

    bool prevHold = m_flags.onBit(eFlags::ItemButtonHold);
    m_flags.resetBit(eFlags::Unlocked, eFlags::ItemButtonHold, eFlags::ItemButtonActivation,
            eFlags::ItemButtonRelease);

    const auto &currentInputs = inputs()->currentState();
    if (!currentInputs.item()) {
        if (prevHold) {
            m_flags.setBit(eFlags::ItemButtonRelease);
        }
    } else if (!prevHold) {
        m_flags.setBit(eFlags::ItemButtonHold, eFlags::ItemButtonActivation);
    } else {
        m_flags.setBit(eFlags::ItemButtonHold);
    }

    auto &status = KartObjectProxy::status();
    if (status.onBit(Kart::eStatus::Vanished)) {
        return;
    }

    f32 stickX = currentInputs.stick.x;
    if (stickX <= m_smoothedStickX) {
        m_smoothedStickX = std::max(m_smoothedStickX - STICK_RATE, stickX);
    } else {
        m_smoothedStickX = std::min(m_smoothedStickX + STICK_RATE, stickX);
    }

    const EGG::Vector3f &kartPos = pos();
    m_posDelta = kartPos - m_prevPos;
    m_prevPos = kartPos;

    // The game leaves the direction uninitialised when the kart did not move; 0 is used here.
    EGG::Vector3f dir = EGG::Vector3f::zero;
    f32 sq = m_posDelta.ps_squareMag();
    if (sq > 0.0f) {
        dir = m_posDelta * EGG::Mathf::frsqrt(sq);
    }

    f32 pitch = dir.y;
    if (status.onBit(Kart::eStatus::AirtimeOver20)) {
        pitch = std::min(std::max(pitch, -MAX_PITCH), MAX_PITCH);
    }

    bool busy = status.onBit(Kart::eStatus::InAction, Kart::eStatus::ZipperTrick,
            Kart::eStatus::TrickRot);
    f32 base = busy ? 0.0f : componentZAxis().y;
    f32 p = (base + move()->speedRatioCapped() * (pitch - base)) * PITCH_SCALE;
    m_throwPitch += PITCH_RATE * ((0.0f + p) - m_throwPitch);

    // Status bits that lock the item button: 4, 32, 33, 35, 36, 72, 82, 83, 89, 135 (and
    // 137..146, which Kinoko does not have); 102 also keeps the lockout.
    bool locking = status.onBit(Kart::eStatus::BeforeRespawn, Kart::eStatus::InAction,
            Kart::eStatus::TriggerRespawn, Kart::eStatus::CannonStart, Kart::eStatus::InCannon,
            Kart::eStatus::NoKartCollision72, Kart::eStatus::NoKartCollision82,
            Kart::eStatus::Vanished, Kart::eStatus::NoKartCollision89,
            Kart::eStatus::NoSlipstreamBoost135);

    if (m_flags.offBit(eFlags::Lockout)) {
        if (locking) {
            m_flags.setBit(eFlags::Lockout);
        } else {
            m_flags.resetBit(eFlags::RouletteHeld, eFlags::HasItem, eFlags::HasTrail,
                    eFlags::PressAccepted, eFlags::ReleaseAccepted);
            m_flags.resetBit(static_cast<eFlags>(3));

            f32 stickY = currentInputs.stick.y;
            if (stickY > STICK_ON) {
                m_flags.setBit(eFlags::StickUp);
            } else if (stickY < STICK_OFF) {
                m_flags.resetBit(eFlags::StickUp);
            }

            if (stickY < -STICK_ON) {
                m_flags.setBit(eFlags::StickDown);
            } else if (stickY > -STICK_OFF) {
                m_flags.resetBit(eFlags::StickDown);
            }

            if (m_flags.onBit(eFlags::ItemButtonActivation) && canStartUse()) {
                m_flags.setBit(eFlags::PressAccepted);
            }

            if (m_flags.onBit(eFlags::ReleaseArmed)) {
                m_flags.resetBit(eFlags::ReleaseArmed);
                if (m_flags.offBit(eFlags::ItemButtonHold) && canStartUse()) {
                    m_flags.setBit(eFlags::ReleaseAccepted);
                }
            }

            m_flags.setBit(eFlags::Unlocked);
        }
    } else if (!locking && status.offBit(Kart::eStatus::AfterCannon)) {
        m_flags.resetBit(eFlags::Lockout);
    }

    if (m_trail.objKind() != ItemObjKind::None) {
        m_trail.calc();
    }

    if (m_inventory.id() != ItemId::NONE) {
        if (System::RaceManager::Instance()->player(m_playerIdx).finished()) {
            m_inventory.clearAndDespawn();
        }

        if (m_inventory.id() != ItemId::NONE && m_inventory.dropTimer() == 0 &&
                m_flags.onAllBit(eFlags::Unlocked, eFlags::PressAccepted, eFlags::HasItem) &&
                status.offBit(Kart::eStatus::InAction)) {
            m_trail.use();
            m_flags.resetBit(eFlags::StickUp, eFlags::StickDown);
        }

        m_inventory.calc();
    }

    if (m_roulette.state() != ItemRoulette::State::Idle && m_roulette.calc()) {
        ItemId id = m_roulette.decidedItem();
        bool replaced = m_roulette.replaced();
        m_roulette.finish();

        if (id == ItemId::THUNDER_CLOUD) {
            ItemDirector::Instance()->spawnThunderCloud(static_cast<u8>(m_playerIdx));
        } else {
            // Offline racers have no partner whose triple items would count (ItemDirector +0x18).
            m_inventory.setItem(id, replaced);
        }
    }

    if (m_itemPoint.idx != System::MapdataItemPoint::NONE) {
        constexpr f32 FAR_SQ_DISTANCE = 144000000.0f; // 12000 ^ 2

        const EGG::Vector3f &kartPos = pos();
        static_cast<void>(calcItemPoint(kartPos));
        if (m_itemPoint.pos.ps_sqDistance(kartPos) >= FAR_SQ_DISTANCE) {
            static_cast<void>(calcItemPointFar(kartPos));
        }
    }
}

/// @addr{0x80798584}
/// @brief Whether the button may start or release an item now; also records what is held.
bool KartItem::canStartUse() {
    if (!System::RaceManager::Instance()->isStageReached(System::RaceManager::Stage::Race)) {
        return false;
    }

    auto &status = KartObjectProxy::status();
    if (status.onBit(Kart::eStatus::InAction, Kart::eStatus::Burnout)) {
        return false;
    }

    if (m_trail.objKind() != ItemObjKind::None) {
        m_flags.setBit(eFlags::HasTrail);
    } else if (m_inventory.id() != ItemId::NONE) {
        m_flags.setBit(eFlags::HasItem);
    } else if (m_roulette.state() != ItemRoulette::State::Idle) {
        m_flags.setBit(eFlags::RouletteHeld);
    }

    return true;
}

/// @brief Uses the held item. The game dispatches through its item behaviour table (+0x18 use
/// function, 0x80791910); only the items that act on karts directly are here. Thrown and dropped
/// items go through ItemTrail.
void KartItem::useItem() {
    switch (m_inventory.id()) {
    case ItemId::MUSHROOM:
    case ItemId::TRIPLE_MUSHROOM:
        useMushroom();
        break;
    case ItemId::GOLDEN_MUSHROOM:
        useGolden();
        break;
    case ItemId::STAR:
        useStar();
        break;
    case ItemId::MEGA_MUSHROOM:
        useMega();
        break;
    case ItemId::LIGHTNING:
        useLightning();
        break;
    case ItemId::THUNDER_CLOUD:
        useThunderCloud();
        break;
    case ItemId::BLOOPER:
        useBlooper();
        break;
    case ItemId::POW_BLOCK:
        usePow();
        break;
    case ItemId::BULLET_BILL:
        useBullet();
        break;
    default:
        break;
    }
}

/// @addr{0x80798848}
void KartItem::clear() {
    if (m_inventory.id() != ItemId::NONE) {
        m_inventory.clearAndDespawn();
    }

    if (m_roulette.state() != ItemRoulette::State::Idle) {
        m_roulette.cancel();
    }

    m_roulette.setPending(ItemId::NONE);

    if (m_trail.objKind() != ItemObjKind::None) {
        m_trail.clear();
    }
}

/// @addr{0x807987EC}
/// @brief The thunder cloud over us strikes (not while respawning or vanished).
void KartItem::strikeByThunderCloud() {
    if (KartObjectProxy::status().onBit(Kart::eStatus::TriggerRespawn,
                Kart::eStatus::NoKartCollision40, Kart::eStatus::InRespawn,
                Kart::eStatus::AfterRespawn, Kart::eStatus::NoKartCollision82,
                Kart::eStatus::Vanished, Kart::eStatus::NoKartCollision89)) {
        return;
    }

    move()->applyThunderCloud();
}

/// @addr{0x8079864C}
void KartItem::activateMushroom() {
    move()->activateMushroom();
}

/// @addr{0x80798684}
void KartItem::activateStar() {
    move()->activateStar();
}

/// @addr{0x807986B4}
void KartItem::activateMega() {
    move()->activateMega();
}

/// @addr{0x80798728}
/// @brief Another racer used a lightning.
/// @return Whether it hit us.
bool KartItem::hitByLightning() {
    auto &status = KartObjectProxy::status();
    if (status.onBit(Kart::eStatus::TriggerRespawn, Kart::eStatus::NoKartCollision40,
                Kart::eStatus::InRespawn, Kart::eStatus::AfterRespawn,
                Kart::eStatus::NoKartCollision82, Kart::eStatus::Vanished,
                Kart::eStatus::NoKartCollision89, Kart::eStatus::InCannon)) {
        return false;
    }

    return move()->applyLightning();
}

/// @addr{0x80798A30}
/// @brief Hit by something: the inventory's item (except a thunder cloud) and the items held
/// behind the kart fall off as objects over the next frames.
void KartItem::loseItem() {
    if (m_inventory.id() != ItemId::NONE && m_inventory.dropTimer() == 0 &&
            m_inventory.id() != ItemId::THUNDER_CLOUD) {
        m_inventory.startDrop();
    }

    if (m_roulette.state() != ItemRoulette::State::Idle) {
        m_roulette.cancel();
    }

    if (m_trail.objKind() != ItemObjKind::None && m_trail.dropTimer() == 0 &&
            !m_trail.forcedRelease()) {
        m_trail.startDrop();
    }
}

/// @addr{0x80798B28}
/// @brief A spin or launch drops the items held behind the kart (not the inventory's item).
/// @param singleOnly Only a single held item drops (triple items stay).
void KartItem::dropTrail(bool singleOnly) {
    if (m_trail.objKind() == ItemObjKind::None || m_trail.dropTimer() != 0 ||
            m_trail.forcedRelease()) {
        return;
    }

    if (singleOnly && m_trail.mode() != ItemTrail::Mode::Single) {
        return;
    }

    m_trail.startDrop();
}

/// @addr{0x807B99D4}
void KartItem::setItemPoint(u8 idx, bool moved) {
    m_itemPoint.idx = idx;
    m_itemPoint.moved = moved;
    if (idx != System::MapdataItemPoint::NONE) {
        m_itemPoint.pos = System::CourseMap::Instance()->getItemPoint(idx)->pos();
    }
}

/// @addr{0x807B8A9C}
/// @brief Moves the kart's item point to the nearest of the points up to two links away.
/// @return Whether it moved.
bool KartItem::calcItemPoint(const EGG::Vector3f &kartPos) {
    auto *courseMap = System::CourseMap::Instance();
    u8 cur = m_itemPoint.idx;
    u8 best = cur;
    f32 bestDist = m_itemPoint.pos.ps_sqDistance(kartPos);

    auto consider = [&](u8 idx) {
        f32 dist = courseMap->getItemPoint(idx)->pos().ps_sqDistance(kartPos);
        if (dist < bestDist) {
            bestDist = dist;
            best = idx;
        }
    };

    u8 nextCount = courseMap->getNextItemPointCount(cur);
    for (u8 i = 0; i < nextCount; ++i) {
        u8 a = courseMap->getNextItemPoint(cur, i);
        if (a != best) {
            consider(a);
        }

        u8 count = courseMap->getNextItemPointCount(a);
        for (u8 j = 0; j < count; ++j) {
            u8 b = courseMap->getNextItemPoint(a, j);
            if (b != best) {
                consider(b);
            }
        }

        count = courseMap->getPrevItemPointCount(a);
        for (u8 j = 0; j < count; ++j) {
            u8 b = courseMap->getPrevItemPoint(a, j);
            if (b != cur && b != best) {
                consider(b);
            }
        }
    }

    u8 prevCount = courseMap->getPrevItemPointCount(cur);
    for (u8 i = 0; i < prevCount; ++i) {
        u8 a = courseMap->getPrevItemPoint(cur, i);
        if (a != best) {
            consider(a);
        }

        u8 count = courseMap->getPrevItemPointCount(a);
        for (u8 j = 0; j < count; ++j) {
            u8 b = courseMap->getPrevItemPoint(a, j);
            if (b != best) {
                consider(b);
            }
        }

        count = courseMap->getNextItemPointCount(a);
        for (u8 j = 0; j < count; ++j) {
            u8 b = courseMap->getNextItemPoint(a, j);
            if (b != cur && b != best) {
                consider(b);
            }
        }
    }

    if (best == cur) {
        return false;
    }

    setItemPoint(best, true);
    return true;
}

/// @addr{0x807B8F30}
/// @brief Far from its item point (a shortcut, a respawn): follows the route forward, one point at
/// a time, until a point is nearer than the current one.
/// @return Whether it moved.
bool KartItem::calcItemPointFar(const EGG::Vector3f &kartPos) {
    auto *courseMap = System::CourseMap::Instance();
    u8 cur = m_itemPoint.idx;
    f32 curDist = m_itemPoint.pos.ps_sqDistance(kartPos);
    u16 remaining = courseMap->getItemPointCount();

    u8 best;
    while (true) {
        f32 bestDist = std::numeric_limits<f32>::max();
        best = System::MapdataItemPoint::NONE;

        u8 count = courseMap->getNextItemPointCount(cur);
        for (u8 i = 0; i < count; ++i) {
            u8 a = courseMap->getNextItemPoint(cur, i);
            if (a == best) {
                continue;
            }

            f32 dist = courseMap->getItemPoint(a)->pos().ps_sqDistance(kartPos);
            if (dist < bestDist) {
                bestDist = dist;
                best = a;
            }
        }

        if (bestDist < curDist) {
            break;
        }

        --remaining;
        cur = best;
        if (remaining < 2 || best == m_itemPoint.idx) {
            return false;
        }
    }

    if (best == m_itemPoint.idx) {
        return false;
    }

    setItemPoint(best, true);
    return true;
}

/// @addr{0x80798C38}
/// @brief Driven through an item box: starts the roulette when the inventory is empty.
/// @param humanSetting The box setting used for humans (KMP setting 1).
/// @param cpuSetting The box setting used for CPUs (KMP setting 2).
/// @param isShort A 45-frame roulette (offline only).
void KartItem::startRoulette(u16 humanSetting, u16 cpuSetting, bool isShort) {
    if (m_inventory.id() != ItemId::NONE || m_isRemote) {
        return;
    }

    const auto &player = System::RaceManager::Instance()->player(m_playerIdx);
    if (player.finished()) {
        return;
    }

    u16 setting = m_isHuman ? humanSetting : cpuSetting;
    // 0x807BD374: the place, outside battles.
    u8 rank = player.rank();
    m_roulette.start(setting, rank, m_isHuman, isShort && !ItemRaceFlags::s_online);
}

/// @addr{0x80798DBC}
/// @brief Whether the racer holds a triple shell or banana item, or (unless ignored) is about to
/// get one from the roulette.
bool KartItem::hasTripleItem(bool ignoreRoulette) const {
    if (!ignoreRoulette && m_roulette.state() != ItemRoulette::State::Idle &&
            m_roulette.decidedItem() > ItemId::BULLET_BILL) {
        return true;
    }

    if (m_inventory.id() != ItemId::NONE && m_inventory.id() > ItemId::BULLET_BILL) {
        return true;
    }

    return m_trail.objKind() != ItemObjKind::None && m_trail.itemId() > ItemId::BULLET_BILL;
}

/// @addr{0x807A9D3C}
void KartItem::useMushroom() {
    activateMushroom();
    m_inventory.useItem(1);
}

/// @addr{0x807A9F64}
/// @brief The first use starts 450 frames of unlimited mushroom boosts.
void KartItem::useGolden() {
    constexpr int GOLDEN_DURATION = 450;
    constexpr int GOLDEN_USE_GAP = 12;

    static_cast<void>(m_inventory.startTimer(GOLDEN_DURATION));
    activateMushroom();
    m_inventory.setTimerUse(GOLDEN_USE_GAP);
}

/// @addr{0x807B706C}
void KartItem::useStar() {
    activateStar();
    m_inventory.useItem(1);
}

/// @addr{0x807A9E50}
void KartItem::useMega() {
    activateMega();
    m_inventory.useItem(1);
}

/// @addr{0x807B7B7C}
void KartItem::useLightning() {
    ItemDirector::Instance()->activateLightning(m_playerIdx);
    ItemSlotData::Instance()->resetLightningTimer();
    m_inventory.useItem(1);
}

/// @addr{0x807AF1BC}
/// @brief A thunder cloud in the inventory (the roulette normally spawns it at once) is put over
/// us.
void KartItem::useThunderCloud() {
    m_inventory.useItem(1);
    ItemDirector::Instance()->spawnThunderCloud(static_cast<u8>(m_playerIdx));
}

/// @addr{0x807A81B4}
void KartItem::useBlooper() {
    ItemDirector::Instance()->blooperManager().activate(static_cast<u8>(m_playerIdx));
    ItemSlotData::Instance()->resetBlooperTimer();
    m_inventory.useItem(1);
}

/// @addr{0x807B1B2C}
void KartItem::usePow() {
    ItemDirector::Instance()->powManager().activate(static_cast<u8>(m_playerIdx));
    ItemSlotData::Instance()->resetPowTimer();
    m_inventory.useItem(1);
}

/// @addr{0x807A9AFC}
void KartItem::useBullet() {
    // 0x807986E4
    move()->activateBullet();
    m_inventory.useItem(1);
    m_roulette.setPending(ItemId::BULLET_BILL);
}

/// @addr{0x80798710}
/// @brief A bullet bill still in the inventory when one ends is dropped.
void KartItem::clearBulletFromInventory() {
    if (m_inventory.id() == ItemId::BULLET_BILL) {
        m_inventory.setId(ItemId::NONE);
    }
}

} // namespace Kinoko::Item
