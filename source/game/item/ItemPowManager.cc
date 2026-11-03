#include "ItemPowManager.hh"

#include "game/kart/KartAction.hh"
#include "game/kart/KartDynamics.hh"
#include "game/kart/KartObject.hh"
#include "game/kart/KartObjectManager.hh"

#include "game/system/RaceManager.hh"

namespace Kinoko::Item {

namespace {

constexpr u8 NO_PLAYER = 12;

} // namespace

ItemPowManager::ItemPowManager() : m_timer(0), m_user(NO_PLAYER) {
    m_targets.fill(false);
}

/// @addr{0x807B1CA8}
void ItemPowManager::init() {
    m_timer = 0;
    m_user = NO_PLAYER;
    m_targets.fill(false);
    // The models are visual.
}

/// @addr{0x807B1DB4}
/// @brief The racers ahead of the user are its targets. Battle teams are left out.
void ItemPowManager::activate(u8 userIdx) {
    constexpr s32 DURATION = 159;

    if (m_timer >= 1) {
        return;
    }

    m_timer = DURATION;
    m_user = userIdx;

    auto *raceMgr = System::RaceManager::Instance();
    u8 userRank = raceMgr->player(userIdx).rank();
    size_t count = Kart::KartObjectManager::Instance()->count();
    for (size_t i = 0; i < count; ++i) {
        m_targets[i] = i != userIdx && !(userRank < raceMgr->player(i).rank());
    }
}

/// @addr{0x807B22F8}
void ItemPowManager::calc() {
    constexpr s32 FIRST_SHAKE = 143;
    constexpr s32 SECOND_SHAKE = 95;
    constexpr s32 LAST_SHAKE = 45;

    if (m_timer <= 0) {
        return;
    }

    --m_timer;
    // Frames 158, 110 and 60 start the block's animations (visual).
    if (m_timer == FIRST_SHAKE) {
        shake(1);
    }

    if (m_timer == SECOND_SHAKE) {
        shake(2);
    }

    if (m_timer == LAST_SHAKE) {
        shake(3);
    }
}

/// @addr{0x807B20BC}
/// @brief One shake: the targets hop on the first two (unless already long in the air); the
/// third strikes them (KartAction::StartPowStrike).
void ItemPowManager::shake(s32 stage) {
    constexpr f32 FIRST_HOP = 6.0f;
    constexpr f32 SECOND_HOP = 10.0f;
    constexpr s32 LAST_STAGE = 3;

    Kart::KartAction::StartPowStrike(static_cast<u8>(stage - 1));

    auto *kartMgr = Kart::KartObjectManager::Instance();
    for (size_t i = 0; i < kartMgr->count(); ++i) {
        auto *kart = kartMgr->object(i);
        kart->action()->setPowAffected(m_targets[i]);

        // The rumble (0x80590F9C) and the HUD (0x806AA508) are left out.
        if (!m_targets[i] || stage >= LAST_STAGE ||
                kart->status().onBit(Kart::eStatus::AirtimeOver20)) {
            continue;
        }

        f32 hop = stage == 1 ? FIRST_HOP : SECOND_HOP;
        auto *dynamics = kart->dynamics();
        dynamics->setExtVel(dynamics->extVel() + EGG::Vector3f(0.0f, hop, 0.0f));
    }

    // The screen shake and the sounds are left out.
}

} // namespace Kinoko::Item
