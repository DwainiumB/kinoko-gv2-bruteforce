#pragma once

#include "game/system/map/MapdataAccessorBase.hh"

#include <egg/math/Vector.hh>

#include <array>

namespace Kinoko::System {

/// @brief A point of the item route (KMP section ITPT), the route the shells follow. Its links to
/// the points before and after it are worked out from the item paths when the map loads.
class MapdataItemPoint {
public:
    struct SData {
        EGG::Vector3f pos;
        f32 width;
        u16 setting1;
        u16 setting2;
    };
    STATIC_ASSERT(sizeof(SData) == 0x14);

    static constexpr size_t MAX_LINKS = 6;
    static constexpr u8 NONE = 0xFF;

    MapdataItemPoint(const SData *data);
    void read(EGG::Stream &stream);
    void initLinks(u8 idx);

    /// @beginGetters
    [[nodiscard]] const EGG::Vector3f &pos() const {
        return m_pos;
    }

    /// @brief The second KMP setting (+0x12): its tens digit marks routes the shells avoid.
    /// @brief The route's half-width around the point, in units of 50 (+0x0C).
    [[nodiscard]] f32 deviation() const {
        return m_deviation;
    }

    /// @brief The bullet bill's control setting (+0x10).
    [[nodiscard]] u16 setting1() const {
        return m_setting1;
    }

    [[nodiscard]] u16 setting2() const {
        return m_setting2;
    }

    [[nodiscard]] u8 prevCount() const {
        return m_prevCount;
    }

    [[nodiscard]] u8 nextCount() const {
        return m_nextCount;
    }

    [[nodiscard]] u8 prev(size_t i) const {
        return m_prev[i];
    }

    [[nodiscard]] u8 next(size_t i) const {
        return m_next[i];
    }
    /// @endGetters

private:
    [[maybe_unused]] const SData *m_rawData; ///< +0x00
    std::array<u8, MAX_LINKS> m_prev;        ///< +0x04
    std::array<u8, MAX_LINKS> m_next;        ///< +0x0A
    u8 m_prevCount;                          ///< +0x10
    u8 m_nextCount;                          ///< +0x11
    EGG::Vector3f m_pos;
    f32 m_deviation;
    u16 m_setting1;
    u16 m_setting2;
};

class MapdataItemPointAccessor
    : public MapdataAccessorBase<MapdataItemPoint, MapdataItemPoint::SData> {
public:
    MapdataItemPointAccessor(const MapSectionHeader *header);
    ~MapdataItemPointAccessor() override;
};

} // namespace Kinoko::System
