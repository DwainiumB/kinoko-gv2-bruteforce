#pragma once

#include "game/field/obj/ObjectCollidable.hh"

namespace Kinoko::Field {

class ObjectCarTGE;

class ObjectHighwayManager : public ObjectCollidable {
public:
    ObjectHighwayManager();
    ~ObjectHighwayManager() override;

    void init() override;
    void calc() override;

    /// @addr{0x806D5C6C}
    [[nodiscard]] u32 loadFlags() const override {
        return 1;
    }

    /// @addr{0x806D5C68}
    void loadGraphics() override {}

    /// @addr{0x806D5C60}
    void createCollision() override {}

    /// @addr{0x806D5C64}
    void loadRail() override {}

    /// @brief Frames since a car last squashed this player (+0x120, one per player, up to 600).
    [[nodiscard]] u32 squashTimer(size_t playerIdx) const {
        return m_squashTimers[playerIdx];
    }

private:
    void calcSquash();

    owning_span<ObjectCarTGE *> m_cars;
    std::array<u32, 12> m_squashTimers; ///< +0x120
    size_t m_playerCount;               ///< +0x100

    static constexpr u32 SQUASH_MAX = 600;
};

} // namespace Kinoko::Field
