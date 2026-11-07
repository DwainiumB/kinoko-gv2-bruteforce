// GPU spike runtime: the device-side "host system" (what main.cc + KSearchSystem do on the CPU), compiled at the end of
// the unity translation unit that run_gpu.py builds from the transformed engine sources.
//
// Memory: the template race owns a full game heap (`space`, MEMORY_SPACE_SIZE bytes) followed by its statics block.
// Clones ("slots") copy only the first R bytes of the heap plus the statics block, relocating every 8-byte word that
// points into the template's copied range; pointers beyond R keep pointing at the template (course data, parameters).

#include <game/field/CourseColMgr.hh>
#include <game/kart/CollisionGroup.hh>
#include <game/kart/KartPhysics.hh>
#include <game/kart/KartBoost.hh>
#include <game/kart/KartHalfPipe.hh>
#include <game/kart/KartMove.hh>
#include <game/kart/KartState.hh>
#include <game/kart/KartObjectManager.hh>
#include <game/system/KPadDirector.hh>
#include <game/system/RaceConfig.hh>
#include <game/system/RaceManager.hh>
#include <egg/core/ExpHeap.hh>
#include <egg/core/SceneManager.hh>
#include <host/FrameState.hh>
#include <host/SceneCreatorDynamic.hh>

using namespace Kinoko;

constexpr size_t STATICS_BYTES = 64 * KINOKO_STATIC_SLOT;  // >= KINOKO_STATIC_COUNT + our own slots
constexpr int SLOT_SCENE_MGR = 60;                          // our own per-race slot: the race's SceneManager *

__device__ char *g_raceBase;           // race 0's base address
__device__ unsigned long long g_raceStride;     // bytes between consecutive races
__device__ unsigned long long g_staticsOffset;  // statics block offset from a race's base

extern "C" char *kinoko_race_statics() {
    unsigned long long tid = blockIdx.x * blockDim.x + threadIdx.x;
    return g_raceBase + tid * g_raceStride + g_staticsOffset;
}

static EGG::SceneManager *&SceneMgr() {
    return *reinterpret_cast<EGG::SceneManager **>(kinoko_race_statics() + SLOT_SCENE_MGR * KINOKO_STATIC_SLOT);
}

__device__ int g_course, g_character, g_vehicle;
__device__ int g_driftAuto = 0;  // 1 = automatic drift (set from the host before k_init)

static void OnInit(System::RaceConfig *config, void *) {
    auto &scenario = config->raceScenario();
    scenario.course = static_cast<Course>(g_course);
    scenario.playerCount = 1;
    auto &player = scenario.players[0];
    player.type = System::RaceConfig::Player::Type::Local;
    player.character = static_cast<Character>(g_character);
    player.vehicle = static_cast<Vehicle>(g_vehicle);
    player.driftIsAuto = g_driftAuto != 0;
}

extern "C" __global__ void k_init(char *space, unsigned long long size, int course, int character, int vehicle) {
    g_raceBase = space;
    g_raceStride = 0;
    g_staticsOffset = size;
    g_course = course;
    g_character = character;
    g_vehicle = vehicle;
    kinoko_statics_init();

    EGG::Heap *root = EGG::ExpHeap::create(space, size, DEFAULT_OPT);
    root->setName("EGGRoot");
    root->becomeCurrentHeap();
    EGG::SceneManager::SetRootHeap(root);

    auto *sceneCreator = EGG::egg_new<Host::SceneCreatorDynamic>();
    SceneMgr() = EGG::egg_new<EGG::SceneManager>(sceneCreator);
    System::RaceConfig::RegisterInitCallback(OnInit, nullptr);
    SceneMgr()->changeScene(0);
}

/// Point the per-race globals at a layout: `base` + tid * `stride`, statics at `staticsOffset`.
extern "C" __global__ void k_layout(char *base, unsigned long long stride, unsigned long long staticsOffset) {
    g_raceBase = base;
    g_raceStride = stride;
    g_staticsOffset = staticsOffset;
}

/// Copy `src` (heap range [srcHeap, srcHeap + r) and statics block srcStatics) into slot `blockIdx.x` of the slot array
/// (slot = r heap bytes then the statics block), relocating pointers. One block of 256 threads per slot.
extern "C" __global__ void k_clone(const char *srcHeap, const char *srcStatics, unsigned long long r, char *slots,
                                   unsigned long long stride, int nslots) {
    int slot = blockIdx.x;
    if (slot >= nslots) {
        return;
    }
    char *dst = slots + slot * stride;
    const unsigned long long sh = reinterpret_cast<unsigned long long>(srcHeap);
    const unsigned long long ss = reinterpret_cast<unsigned long long>(srcStatics);
    const unsigned long long dh = reinterpret_cast<unsigned long long>(dst);
    const unsigned long long ds = dh + r;
    auto reloc = [&](unsigned long long v) -> unsigned long long {
        if (v >= sh && v < sh + r) {
            return v - sh + dh;
        }
        if (v >= ss && v < ss + STATICS_BYTES) {
            return v - ss + ds;
        }
        return v;
    };
    const auto *srcWords = reinterpret_cast<const unsigned long long *>(srcHeap);
    auto *dstWords = reinterpret_cast<unsigned long long *>(dst);
    for (unsigned long long i = threadIdx.x; i < r / 8; i += blockDim.x) {
        dstWords[i] = reloc(srcWords[i]);
    }
    const auto *srcS = reinterpret_cast<const unsigned long long *>(srcStatics);
    auto *dstS = reinterpret_cast<unsigned long long *>(dst + r);
    for (unsigned long long i = threadIdx.x; i < STATICS_BYTES / 8; i += blockDim.x) {
        dstS[i] = reloc(srcS[i]);
    }
}

struct StepInput {
    int buttons;
    float stickX, stickY;
    int trick;
};

/// Step every race `frames` frames; race i reads inputs[(frame) * stride_in + i * per_race_in].
extern "C" __global__ void k_step(const StepInput *inputs, int frames, int nraces, int perRace) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if (tid >= nraces) {
        return;
    }
    for (int f = 0; f < frames; ++f) {
        const StepInput &in = inputs[f * (perRace ? nraces : 1) + (perRace ? tid : 0)];
        auto *padDir = System::KPadDirector::Instance();
        auto *host = padDir ? padDir->hostController() : nullptr;
        if (host) {
            host->setInputs(static_cast<u16>(in.buttons), EGG::Vector2f(in.stickX, in.stickY),
                    static_cast<System::Trick>(in.trick));
        }
        SceneMgr()->calc();
    }
}

constexpr int STATE_WORDS = 26;

/// Per race: stage raceFrame checkpoint driftState mtCharge, then px py pz qx qy qz qw mqx mqy mqz mqw evx evy evz ivx
/// ivy ivz speed speedRatio kclSpeedFactor completion (floats as raw bits).
extern "C" __global__ void k_state(unsigned int *out, int nraces) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if (tid >= nraces) {
        return;
    }
    unsigned int *o = out + tid * STATE_WORDS;
    const auto *race = System::RaceManager::Instance();
    auto *object = Kart::KartObjectManager::Instance()->object(0);
    const auto *move = object->move();
    const auto &player = race->player();
    o[0] = static_cast<unsigned int>(race->stage());
    o[1] = race->timer();
    o[2] = player.checkpointId();
    o[3] = static_cast<unsigned int>(move->driftState());
    o[4] = static_cast<unsigned int>(move->mtCharge());
    const auto &pos = object->pos();
    const auto &rot = object->fullRot();
    const auto &mainRot = object->mainRot();
    const auto &ev = object->extVel();
    const auto &iv = object->intVel();
    float f[] = {pos.x, pos.y, pos.z, rot.v.x, rot.v.y, rot.v.z, rot.w, mainRot.v.x, mainRot.v.y, mainRot.v.z,
            mainRot.w, ev.x, ev.y, ev.z, iv.x, iv.y, iv.z, move->speed(), move->speedRatio(), move->kclSpeedFactor(),
            player.raceCompletion()};
    for (int i = 0; i < 21; ++i) {
        o[5 + i] = __float_as_uint(f[i]);
    }
}

__device__ double *g_captureBase;

extern "C" double *kinoko_capture_buffer() {
    unsigned long long tid = blockIdx.x * blockDim.x + threadIdx.x;
    return g_captureBase + tid * KINOKO_CAPTURE_DOUBLES;
}

/// Every race of the current layout: run the CPU build's own state-row writer (host/FrameState.cc). out is
/// [nraces][KINOKO_CAPTURE_DOUBLES]: [0] = value count (109), [1..109] the row, then [120] stage, [121] the player's
/// race timer in ms (what kinoko_host reports as END timeMs), [122] = frame. [110..116] are the extra fields
/// KBruteSystem::reportResult prints (and tools/gpu_brute.py scores): boostCharge, boostMultiplier, frontX/Y/Z
/// (bodyFront), inStunt, inTrick; [117] smtCharge, [118] wheels with floor contact, [119] their bit mask.
extern "C" __global__ void k_rows(double *out, unsigned int frame, int nraces) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if (tid >= nraces) {
        return;
    }
    g_captureBase = out;  // every thread stores the same value
    double *b = out + static_cast<unsigned long long>(tid) * KINOKO_CAPTURE_DOUBLES;
    b[0] = 0;
    Host::WriteStateRow(stdout, frame, "");
    const auto *race = System::RaceManager::Instance();
    const auto &t = race->player().raceTimer();
    b[120] = static_cast<double>(race->stage());
    b[121] = static_cast<double>(static_cast<int>(t.min) * 60000 + static_cast<int>(t.sec) * 1000 + static_cast<int>(t.mil));
    b[122] = frame;
    const auto *kart = Kart::KartObjectManager::Instance()->object(0);
    const EGG::Vector3f front = kart->bodyFront();
    b[110] = static_cast<double>(kart->state()->startBoostCharge());
    b[111] = static_cast<double>(kart->move()->boost().multiplier());
    b[112] = static_cast<double>(front.x);
    b[113] = static_cast<double>(front.y);
    b[114] = static_cast<double>(front.z);
    b[115] = kart->halfPipe() && kart->halfPipe()->isInStunt() ? 1.0 : 0.0;
    b[116] = kart->state()->status().onBit(Kart::eStatus::InATrick) ? 1.0 : 0.0;
    b[117] = static_cast<double>(kart->move()->smtCharge());  // super mini-turbo charge 0..300 (state 2 charging, 3 charged)
    {
        // wheels with floor contact (same test as the host's dump columns floor0..3): [118] count, [119] bit mask by tire index
        const u16 tires = kart->tireCount();
        int count = 0, mask = 0;
        for (u16 i = 0; i < tires && i < 4; ++i) {
            const auto &cd = kart->collisionData(i);
            if (cd.bFloor && cd.closestFloorFlags) {
                ++count;
                mask |= 1 << i;
            }
        }
        b[118] = static_cast<double>(count);
        b[119] = static_cast<double>(mask);
    }
}

/// Wall proximity of every race of the current layout, by the game's own driver-wall collision test: for each of two
/// wall families (visible: wall, wall 2, player wall, special wall; invisible: invisible wall, invisible wall 2) the
/// smallest extra radius (units; 0 = touching) at which any of the kart's hitbox spheres overlaps such a triangle, 300 if
/// none within 240. out[2*tid] = visible, out[2*tid+1] = invisible. Uses the hitboxes' world positions of the last frame.
/// Read-only for the race: stepping with and without probing ends in the same state (tools/probe_check.py).
extern "C" __global__ void k_probe(float *out, int nraces) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if (tid >= nraces) {
        return;
    }
    const float margins[] = {0.0f, 25.0f, 50.0f, 80.0f, 120.0f, 170.0f, 240.0f};
    const Field::KCLTypeMask masks[2] = {
            KCL_TYPE_BIT(COL_TYPE_WALL) | KCL_TYPE_BIT(COL_TYPE_WALL_2) | KCL_TYPE_BIT(COL_TYPE_PLAYER_WALL) |
                    KCL_TYPE_BIT(COL_TYPE_SPECIAL_WALL),
            KCL_TYPE_BIT(COL_TYPE_INVISIBLE_WALL) | KCL_TYPE_BIT(COL_TYPE_INVISIBLE_WALL2)};
    float best[2] = {300.0f, 300.0f};
    auto *kart = Kart::KartObjectManager::Instance()->object(0);
    auto *group = kart->physics()->hitboxGroup();
    auto *mgr = Field::CourseColMgr::Instance();
    for (u16 h = 0; h < group->hitboxCount(); ++h) {
        auto &hb = group->hitbox(h);
        for (int k = 0; k < 2; ++k) {
            for (float m : margins) {
                if (m >= best[k]) {
                    break;
                }
                Field::KCLTypeMask maskOut = 0;
                if (mgr->checkSphereFull(1.0f, hb.radius() + m, nullptr, hb.worldPos(), hb.worldPos(), masks[k], nullptr,
                            &maskOut)) {
                    best[k] = m;
                    break;
                }
            }
        }
    }
    out[2 * tid] = best[0];
    out[2 * tid + 1] = best[1];
}

/// Relocating slot-to-slot copies: block b copies the slot at src[b] (r heap bytes, then the statics block) to dst[b].
extern "C" __global__ void k_copy_slots(const unsigned long long *src, const unsigned long long *dst,
                                        unsigned long long r, int n) {
    int b = blockIdx.x;
    if (b >= n) {
        return;
    }
    const unsigned long long s = src[b], d = dst[b], size = r + STATICS_BYTES;
    const auto *sw = reinterpret_cast<const unsigned long long *>(s);
    auto *dw = reinterpret_cast<unsigned long long *>(d);
    for (unsigned long long i = threadIdx.x; i < size / 8; i += blockDim.x) {
        unsigned long long v = sw[i];
        dw[i] = (v >= s && v < s + size) ? v - s + d : v;
    }
}
