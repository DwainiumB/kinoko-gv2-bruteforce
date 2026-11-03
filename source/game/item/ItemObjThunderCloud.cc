#include "ItemObjThunderCloud.hh"

#include "game/item/ItemDirector.hh"

#include "game/kart/KartMove.hh"
#include "game/kart/KartObject.hh"
#include "game/kart/KartObjectManager.hh"

namespace Kinoko::Item {

namespace {

constexpr u8 NO_PLAYER = 12;

/// The cloud starts this high over the carrier (0x808A5E88); the rest of its motion is visual.
constexpr f32 HEIGHT = 600.0f;

Kart::KartObject *Kart(u8 idx) {
    return Kart::KartObjectManager::Instance()->object(idx);
}

/// @addr{0x80591314}
bool IsUntargetable(const Kart::KartObject *kart) {
    return kart->status().onBit(Kart::eStatus::TriggerRespawn, Kart::eStatus::InRespawn,
            Kart::eStatus::AfterRespawn, Kart::eStatus::Vanished);
}

/// @brief The racer cannot carry the cloud now (respawning, in a cannon, star, mega or bullet).
/// KartItem +0x240 (an item immunity timer) is not ported and taken as 0.
bool CannotCarry(const Kart::KartObject *kart) {
    return IsUntargetable(kart) ||
            kart->status().onBit(Kart::eStatus::InCannon, Kart::eStatus::InStar,
                    Kart::eStatus::InMega, Kart::eStatus::InBullet);
}

} // namespace

ItemObjThunderCloud::ItemObjThunderCloud()
    : m_carrier(0), m_lastCarrier(NO_PLAYER), m_passCount(0), m_passTimer(0), m_strikeTimer(0) {}

ItemObjThunderCloud::~ItemObjThunderCloud() = default;

/// @addr{0x807AF234}
/// @brief Settles over the racer who drew it.
void ItemObjThunderCloud::onSpawn() {
    constexpr s32 PASS_DELAY = 5;

    m_carrier = m_owner;
    Kart(m_carrier)->move()->activateThunderCloud();
    m_passCount = 0;
    m_lastCarrier = NO_PLAYER;

    m_pos = Kart(m_carrier)->pos();
    m_pos.y += HEIGHT;
    // The smoothed position, sway and model fields are visual.

    m_passTimer = PASS_DELAY;
    m_strikeTimer = 0;
    // flags2 bit 4 is not used by the ported code.
}

/// @addr{0x807AF76C}
void ItemObjThunderCloud::calcThunderCloud() {
    constexpr s32 CHECK_FRAME = 30;
    constexpr s32 STRIKE_FRAME = 600;
    constexpr s32 BREAK_FRAME = 690;

    const auto *kart = Kart(m_carrier);
    m_pos = kart->pos();
    m_pos.y += HEIGHT;

    if (m_flags.onBit(eFlags::Breaking)) {
        calcBreaking();
        return;
    }

    // Frame 60 clears a thunder cloud left in the inventory (KartItem +0x1A, not ported).

    if (m_frame > CHECK_FRAME && CannotCarry(kart)) {
        // The online check (RaceManager player +0x38 bit 1) and remote racers are left out.
        startBreak(true);
        Kart(m_carrier)->move()->deactivateThunderCloud();
        return;
    }

    if (++m_strikeTimer == STRIKE_FRAME) {
        Kart(m_carrier)->move()->deactivateThunderCloud();
        ItemDirector::Instance()->kartItem(m_carrier).strikeByThunderCloud();
        // The battle statistics and the sound are left out.
    }

    --m_passTimer;
    // The flashes and the sounds before the strike are visual.

    if (m_strikeTimer > BREAK_FRAME) {
        startBreak(false);
    }
}

/// @addr{0x807B0B4C}
/// @brief The carrier bumped into another racer: the cloud moves over to them, unless it just
/// changed hands, is about to strike, or they cannot carry it.
void ItemObjThunderCloud::passTo(u8 playerIdx) {
    constexpr s32 LAST_PASS_FRAME = 598;
    constexpr s32 MAX_PASSES = 0xFF;

    if (m_passTimer >= 1) {
        return;
    }

    // The battle team check is left out.
    if (m_strikeTimer >= LAST_PASS_FRAME) {
        return;
    }

    if (CannotCarry(Kart(playerIdx))) {
        return;
    }

    // The online paths (flags2 bit 5) are left out. The spark effect between the two racers and
    // the carrier's rumble are visual.

    if (m_passCount != MAX_PASSES) {
        handOver(playerIdx);
    }
}

/// @addr{0x807B1108}
void ItemObjThunderCloud::handOver(u8 playerIdx) {
    constexpr s32 PASS_DELAY = 45;
    constexpr s32 MAX_TIMER = 480;

    ++m_passCount;
    Kart(m_carrier)->move()->deactivateThunderCloud();
    m_lastCarrier = m_carrier;
    m_carrier = playerIdx;
    Kart(m_carrier)->move()->activateThunderCloud();
    // The sound is left out.

    m_passTimer = PASS_DELAY;
    m_strikeTimer = std::min(m_strikeTimer, MAX_TIMER);
    // The sway and flash fields are visual.
}

ItemObj::StateFunc ItemObjThunderCloud::initialState() const {
    return static_cast<StateFunc>(&ItemObjThunderCloud::calcThunderCloud);
}

} // namespace Kinoko::Item
