#include "RaceManager.hh"

#include "game/system/CourseMap.hh"
#include "game/system/KPadDirector.hh"
#include "game/system/RaceConfig.hh"
#include "game/system/map/MapdataCheckPath.hh"
#include "game/system/map/MapdataStartPoint.hh"

#include "game/kart/KartObjectManager.hh"
#include "game/kart/KartState.hh"

namespace Kinoko::System {

/// @addr{0x80532F88}
void RaceManager::init() {
    m_slipstreamTurn = 0x80000000;
    m_playerCount = RaceConfig::Instance()->raceScenario().playerCount;
    for (size_t i = 0; i < m_playerCount; ++i) {
        m_players[i].init(static_cast<u8>(i));
    }
}

/// @addr{0x805362DC}
void RaceManager::findKartStartPoint(u8 idx, EGG::Vector3f &pos, EGG::Vector3f &angles) {
    // VS: the place the menus gave this player (RaceManager::Player +0x20 in the game, copied from
    // the race config). Kinoko has no game modes; one racer gets place 1 of 1 as in Time Trials.
    const auto &scenario = RaceConfig::Instance()->raceScenario();
    u8 startPlacement = scenario.players[idx].startPlacement;
    u32 placement = startPlacement > 0 ? startPlacement : idx + 1;
    u32 playerCount = scenario.playerCount;
    u32 startPointIdx = 0;

    MapdataStartPoint *kartpoint = CourseMap::Instance()->getStartPoint(startPointIdx);

    if (kartpoint) {
        kartpoint->findKartStartPoint(pos, angles, placement - 1, playerCount);
    } else {
        pos.setZero();
        angles = EGG::Vector3f::ex;
    }
}

/// @addr{0x80533C6C}
void RaceManager::endPlayerRace(u32 idx) {
    m_players[idx].m_finished = true;

    // The race is over for everyone once every player has crossed the line; before that, the local
    // player (0) having finished is FinishLocal
    bool all = true;
    for (size_t i = 0; i < m_playerCount; ++i) {
        all = all && m_players[i].m_finished;
    }
    if (all) {
        m_stage = Stage::FinishGlobal;
    } else if (idx == 0) {
        m_stage = Stage::FinishLocal;
    }
}

/// @addr{0x805331B4}
void RaceManager::calc() {
    constexpr u16 STAGE_INTRO_DURATION = 172;

    m_timerManager.calc();
    for (size_t i = 0; i < m_playerCount; ++i) {
        m_players[i].calc();
    }

    calcRanks();

    switch (m_stage) {
    case Stage::Intro:
        if (++m_introTimer >= STAGE_INTRO_DURATION) {
            m_stage = Stage::Countdown;
            KPadDirector::Instance()->startGhostProxies();
        }
        break;
    case Stage::Countdown:
        calcSlipstreamTurn();
        if (++m_timer >= STAGE_COUNTDOWN_DURATION) {
            m_timerManager.setStarted(true);
            m_stage = Stage::Race;
        }
        break;
    case Stage::Race:
        calcSlipstreamTurn();
        ++m_timer;
        break;
    default:
        calcSlipstreamTurn();
        break;
    }
}

/// @addr{0x805336D8}
/// @brief Ranks the racers by race completion, finished racers first by finish time. An insertion
/// sort that starts from last frame's order, so ties keep it.
void RaceManager::calcRanks() {
    constexpr f64 FINISHED_INDEX_FACTOR = static_cast<f64>(0.01f);
    constexpr f64 FINISHED_BASE = 6000099.0;

    std::array<f64, MAX_PLAYERS> scores;
    std::array<u8, MAX_PLAYERS> order;

    for (size_t i = 0; i < m_playerCount; ++i) {
        const Player &player = m_players[i];
        size_t slot = player.m_rank - 1;

        if (player.m_finished) {
            const Timer &time = player.m_raceTimer;
            u32 min = time.min < 100 ? time.min : 99;
            u32 sec = time.min < 100 ? time.sec : 59;
            u32 mil = time.min < 100 ? time.mil : 999;
            u32 timeMs = mil + (sec + min * 60) * 1000;
            scores[slot] = FINISHED_INDEX_FACTOR * static_cast<f64>(static_cast<u32>(i)) +
                    (FINISHED_BASE - static_cast<f64>(timeMs));
        } else {
            scores[slot] = static_cast<f64>(player.m_raceCompletion);
        }

        order[slot] = static_cast<u8>(i);
    }

    for (size_t i = 1; i < m_playerCount; ++i) {
        f64 score = scores[i];
        u8 idx = order[i];
        size_t j = i;
        for (; j > 0 && scores[j - 1] < score; --j) {
            scores[j] = scores[j - 1];
            order[j] = order[j - 1];
        }

        scores[j] = score;
        order[j] = idx;
    }

    for (size_t i = 0; i < m_playerCount; ++i) {
        m_players[order[i]].m_rank = static_cast<u8>(i + 1);
    }
}

/// @addr{0x8055070C}
/// @brief Passes the slipstream search to the next of the 12 slots, wrapping to slot 0.
void RaceManager::calcSlipstreamTurn() {
    u32 next = (m_slipstreamTurn >> 1) & m_slipstreamSlots;
    m_slipstreamTurn = next != 0 ? next : 0x80000000;
}

/// @addr{0x8053621C}
MapdataJugemPoint *RaceManager::jugemPoint(u8 idx) const {
    s8 jugemId = std::max<s8>(m_players[idx].jugemId(), 0);
    return System::CourseMap::Instance()->getJugemPoint(static_cast<u16>(jugemId));
}

/// @addr{0x80532084}
RaceManager *RaceManager::CreateInstance() {
    ASSERT(!s_instance);
    s_instance = EGG::egg_new<RaceManager>();
    return s_instance;
}

/// @addr{0x805320D4}
void RaceManager::DestroyInstance() {
    ASSERT(s_instance);
    auto *instance = s_instance;
    s_instance = nullptr;
    EGG::egg_delete(instance);
}

/// @addr{0x805327A0}
RaceManager::RaceManager()
    : m_random(RaceConfig::Instance()->raceScenario().seed1),
      m_random2(RaceConfig::Instance()->raceScenario().seed2), m_playerCount(0),
      m_stage(Stage::Intro), m_introTimer(0), m_timer(0), m_slipstreamSlots(0xFFF00000),
      m_slipstreamTurn(0x80000000) {}

/// @addr{0x80532E3C}
RaceManager::~RaceManager() {
    if (s_instance) {
        s_instance = nullptr;
        WARN("RaceManager instance not explicitly handled!");
    }
}

/// @addr{0x80533ED8}
RaceManager::Player::Player() {
    m_checkpointId = 0;
    m_raceCompletion = 0.0f;
    m_checkpointFactor = -1.0f;
    m_checkpointStartLapCompletion = 0.0f;
    m_lapCompletion = 0.999999f;

    auto *courseMap = CourseMap::Instance();

    if (courseMap->getCheckPointCount() > 0 && courseMap->getCheckPathCount() > 0) {
        m_maxKcp = courseMap->checkPoint()->lastKcpType();
    } else {
        m_maxKcp = -1;
    }

    m_currentLap = 0;
    m_maxLap = 1;
    m_drivingWrongWay = false;
    m_idx = 0;
    m_finished = false;
    m_inputs = &KPadDirector::Instance()->playerInput(0);
    m_startRandomBit = 0; // The game leaves it unset until init.
}

/// @addr{0x80534194}
void RaceManager::Player::init(u8 idx) {
    constexpr u32 START_BIT_RANGE = 10;

    // 0x805341C4: the first thing each player's init does is one draw from the race's second
    // generator. The players are initialised in index order.
    m_startRandomBit = 1u << (RaceManager::Instance()->random2().getU32(START_BIT_RANGE) + 1);

    m_idx = idx;
    // The RaceManager constructor (0x805327A0) starts each rank at the race config's grid place.
    u8 startPlacement = RaceConfig::Instance()->raceScenario().players[idx].startPlacement;
    m_rank = startPlacement > 0 ? startPlacement : static_cast<u8>(idx + 1);
    m_inputs = &KPadDirector::Instance()->playerInput(idx);
    auto *courseMap = CourseMap::Instance();

    if (courseMap->getCheckPointCount() != 0 && courseMap->getCheckPathCount() != 0) {
        const EGG::Vector3f &pos = Kart::KartObjectManager::Instance()->object(m_idx)->pos();
        f32 distanceRatio;
        s16 checkpointId = courseMap->findSector(pos, 0, distanceRatio);

        m_checkpointId = std::max<s16>(0, checkpointId);
        m_jugemId = courseMap->getCheckPoint(m_checkpointId)->jugemIndex();
    } else {
        m_jugemId = 0;
    }
}

/// @addr{0x80535304}
void RaceManager::Player::calc() {
    auto *courseMap = CourseMap::Instance();
    const auto *kart = Kart::KartObjectManager::Instance()->object(m_idx);

    if (courseMap->getCheckPointCount() == 0 || courseMap->getCheckPathCount() == 0 ||
            kart->status().onBit(Kart::eStatus::BeforeRespawn)) {
        return;
    }

    f32 distanceRatio;
    s16 checkpointId = courseMap->findSector(kart->pos(), m_checkpointId, distanceRatio);

    if (checkpointId == -1) {
        return;
    }

    System::MapdataCheckPoint *checkpoint = nullptr;

    if (m_checkpointFactor < 0.0f || m_checkpointId != checkpointId) {
        checkpoint = calcCheckpoint(checkpointId, distanceRatio);
    } else {
        checkpoint = CourseMap::Instance()->getCheckPoint(m_checkpointId);
    }

    m_raceCompletion = static_cast<f32>(m_currentLap) +
            (m_checkpointStartLapCompletion + m_checkpointFactor * distanceRatio);
    m_raceCompletion = std::min(m_raceCompletion, static_cast<f32>(m_currentLap) + 0.99999f);

    const EGG::Vector3f &bodyFront = kart->bodyFront();
    if (bodyFront.x != 0.0f && bodyFront.z != 0.0f) {
        EGG::Vector2f frontXZ = EGG::Vector2f(bodyFront.x, bodyFront.z);
        frontXZ.normalise();
        m_drivingWrongWay = checkpoint->dir().dot(frontXZ) <= -0.5f;
    }
}

/// @addr{0x8053572C}
/// @brief Gets the lap split, which is the difference between the given lap and the previous one.
/// @param lap One-indexed lap.
/// @return The split timer.
Timer RaceManager::Player::getLapSplit(size_t lap) const {
    ASSERT(lap <= m_lapTimers.size());

    if (lap < 2) {
        return m_lapTimers[0];
    }

    const Timer &currentLap = m_lapTimers[lap - 1];
    const Timer &previousLap = m_lapTimers[lap - 2];
    if (!currentLap.valid || !previousLap.valid) {
        return Timer(std::numeric_limits<u16>::max(), 0, 0);
    }

    return currentLap - previousLap;
}

/// @addr{0x80534DF8}
MapdataCheckPoint *RaceManager::Player::calcCheckpoint(u16 checkpointId, f32 distanceRatio) {
    auto *courseMap = CourseMap::Instance();

    u16 oldCheckpointId = m_checkpointId;
    m_checkpointId = checkpointId;

    f32 lapProportion = courseMap->checkPath()->lapProportion();
    MapdataCheckPath *checkPath = courseMap->checkPath()->findCheckpathForCheckpoint(checkpointId);
    m_checkpointFactor = checkPath->oneOverCount() * lapProportion;

    m_checkpointStartLapCompletion = static_cast<f32>(checkPath->depth()) * lapProportion +
            (m_checkpointFactor * static_cast<f32>(checkpointId - checkPath->start()));

    f32 newLapCompletion = m_checkpointStartLapCompletion + distanceRatio * m_checkpointFactor;
    f32 deltaLapCompletion = m_lapCompletion - newLapCompletion;

    MapdataCheckPoint *newCheckpoint = courseMap->getCheckPoint(checkpointId);
    const MapdataCheckPoint *oldCheckpoint = courseMap->getCheckPoint(oldCheckpointId);

    s8 newJugemIdx = newCheckpoint->jugemIndex();
    if (newJugemIdx >= 0) {
        m_jugemId = newJugemIdx;
    }

    if (!newCheckpoint->isNormalCheckpoint()) {
        if (newCheckpoint->checkArea() > m_maxKcp) {
            m_maxKcp = newCheckpoint->checkArea();
        } else if (m_maxKcp == courseMap->checkPoint()->lastKcpType()) {
            if ((newCheckpoint->isFinishLine() &&
                        areCheckpointsSubsequent(oldCheckpoint, checkpointId)) ||
                    deltaLapCompletion > 0.95f) {
                incrementLap();
            }
        }
    }

    if ((oldCheckpoint->isFinishLine() &&
                areCheckpointsSubsequent(newCheckpoint, oldCheckpointId)) ||
            deltaLapCompletion < -0.95f) {
        decrementLap();
    }

    m_lapCompletion = newLapCompletion;

    return newCheckpoint;
}

/// @addr{Inlined in 0x80534DF8}
bool RaceManager::Player::areCheckpointsSubsequent(const MapdataCheckPoint *checkpoint,
        u16 nextCheckpointId) const {
    for (size_t i = 0; i < checkpoint->nextCount(); ++i) {
        if (nextCheckpointId == checkpoint->nextPoint(i)->id()) {
            return true;
        }
    }

    return false;
}

/// @addr{0x80534D6C}
void RaceManager::Player::decrementLap() {
    auto *courseMap = CourseMap::Instance();

    if (courseMap->getCheckPointCount() > 0 && courseMap->getCheckPathCount() > 0) {
        m_maxKcp = courseMap->checkPoint()->lastKcpType();
    } else {
        m_maxKcp = -1;
    }

    --m_currentLap;
}

/// @addr{0x805349B8}
void RaceManager::Player::incrementLap() {
    m_maxKcp = 0;
    if (++m_currentLap <= m_maxLap) {
        return;
    }

    const auto *kart = Kart::KartObjectManager::Instance()->object(m_idx);
    u16 addMs = CourseMap::Instance()->getCheckPointEntryOffsetMs(m_checkpointId, kart->pos(),
            kart->prevPos());

    const Timer &currentTimer = RaceManager::Instance()->timerManager().currentTimer();
    Timer timer = currentTimer + static_cast<f32>(addMs);

    // TODO: Handle this case more gracefully
    ASSERT(static_cast<size_t>(m_maxLap - 1) < m_lapTimers.size());
    m_lapTimers[m_maxLap - 1] = timer;

    if (m_maxLap >= 3) {
        endRace(timer);
    } else {
        m_maxLap = m_currentLap;
    }
}

/// @addr{0x805347F4}
void RaceManager::Player::endRace(const Timer &finishTime) {
    m_raceTimer = finishTime;
    RaceManager::Instance()->endPlayerRace(m_idx);
}

RaceManager *RaceManager::s_instance = nullptr; ///< @addr{0x809BD730}

} // namespace Kinoko::System
