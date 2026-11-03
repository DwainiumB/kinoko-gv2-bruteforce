#include "ItemBlooperManager.hh"

#include "game/kart/KartMove.hh"
#include "game/kart/KartObject.hh"
#include "game/kart/KartObjectManager.hh"

#include "game/system/RaceManager.hh"
#include "game/system/ResourceManager.hh"

#include <abstract/g3d/ResFile.hh>

namespace Kinoko::Item {

namespace {

constexpr u8 NO_PLAYER = 12;

/// @brief Each racer's ink delay in steps of 3 frames, by player index (0x808D1DA0).
constexpr std::array<s32, 12> INK_DELAYS = {{3, 1, 4, 11, 5, 9, 2, 6, 10, 8, 7, 0}};

/// @addr{0x80591314}
bool IsUntargetable(const Kart::KartObject *kart) {
    return kart->status().onBit(Kart::eStatus::TriggerRespawn, Kart::eStatus::InRespawn,
            Kart::eStatus::AfterRespawn, Kart::eStatus::Vanished);
}

/// @brief Racers the blooper skips: respawning, in a cannon, star, mega or bullet. KartItem
/// +0x240 (an item immunity timer) is not ported and taken as 0.
bool IsImmune(const Kart::KartObject *kart) {
    return IsUntargetable(kart) ||
            kart->status().onBit(Kart::eStatus::InCannon, Kart::eStatus::InStar,
                    Kart::eStatus::InMega, Kart::eStatus::InBullet);
}

/// @brief The length of the blooper model's "start" animation (`gesso.brres`): the game reads it
/// from the model when the blooper is used.
s32 StartAnimationFrames() {
    const void *file = System::ResourceManager::Instance()->getFile("gesso.brres", nullptr,
            System::ArchiveId::Core);
    ASSERT(file);
    return Abstract::g3d::ResFile(file).resAnmChr("start").frameCount();
}

} // namespace

ItemBlooperManager::ItemBlooperManager() : m_user(NO_PLAYER), m_timer(0), m_targetFrame(0) {
    m_targets.fill(0);
}

/// @addr{0x807A8FD8}
void ItemBlooperManager::init() {
    m_user = NO_PLAYER;
    m_timer = 0;
    m_targetFrame = 0;
    m_targets.fill(0);
    // The models are visual.
}

/// @addr{0x807A81B4}
/// @brief The blooper appears; its targets are chosen when its animation ends.
void ItemBlooperManager::activate(u8 userIdx) {
    constexpr s32 TARGET_DELAY = 30;

    if (m_timer >= 1) {
        return;
    }

    m_timer = 1;
    m_user = userIdx;
    m_targetFrame = StartAnimationFrames() + TARGET_DELAY;
    // The models of the local screens and the sound are visual.
}

/// @addr{0x807A92B0}
void ItemBlooperManager::calc() {
    constexpr f32 INK_DELAY = 148.0f;
    constexpr s32 INK_STEP = 3;

    if (m_timer <= 0) {
        return;
    }

    if (m_timer == m_targetFrame) {
        chooseTargets();
    }

    bool done = true;
    auto *kartMgr = Kart::KartObjectManager::Instance();
    for (size_t i = 0; i < m_targets.size(); ++i) {
        if (m_targets[i] == 0) {
            continue;
        }

        done = false;
        s32 frame = m_targetFrame + INK_DELAYS[i] * INK_STEP;
        if (static_cast<f32>(m_timer) != INK_DELAY + static_cast<f32>(frame)) {
            continue;
        }

        auto *kart = kartMgr->object(i);
        if (!IsImmune(kart)) {
            kart->move()->applyInk(i == m_user);
        }

        m_targets[i] = 0;
    }

    // The HUD and the models are visual.
    ++m_timer;
    if (done && m_timer > m_targetFrame) {
        m_timer = 0;
    }
}

/// @addr{0x807A972C}
/// @brief The racers ahead of the user, unless immune now; the value (3 for ranks 1-4, 2 for
/// 5-8, 1 for 9-12) only drives the models. Battle teams are left out.
void ItemBlooperManager::chooseTargets() {
    constexpr s32 RANKS_PER_STEP = 4;
    constexpr s32 TOP_VALUE = 3;

    m_targets.fill(0);

    auto *raceMgr = System::RaceManager::Instance();
    auto *kartMgr = Kart::KartObjectManager::Instance();
    u8 userRank = raceMgr->player(m_user).rank();
    for (u8 rank = 1; rank < userRank; ++rank) {
        for (size_t i = 0; i < kartMgr->count(); ++i) {
            if (raceMgr->player(i).rank() != rank) {
                continue;
            }

            if (!IsImmune(kartMgr->object(i))) {
                m_targets[i] = TOP_VALUE - (rank - 1) / RANKS_PER_STEP;
            }
        }
    }
}

} // namespace Kinoko::Item
