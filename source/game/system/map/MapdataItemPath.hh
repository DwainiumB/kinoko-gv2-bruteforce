#pragma once

#include "game/system/map/MapdataAccessorBase.hh"

namespace Kinoko::System {

/// @brief A group of consecutive item points (KMP section ITPH), with the groups before and after
/// it.
class MapdataItemPath {
public:
    struct SData {
        u8 start;
        u8 size;
        u8 prev[6];
        u8 next[6];
        u8 _0e[0x10 - 0x0e];
    };
    STATIC_ASSERT(sizeof(SData) == 0x10);

    static constexpr size_t MAX_NEIGHBORS = 6;

    MapdataItemPath(const SData *data);

    /// @beginGetters
    [[nodiscard]] u8 start() const {
        return m_rawData->start;
    }

    [[nodiscard]] u8 end() const {
        return m_rawData->start + m_rawData->size - 1;
    }

    [[nodiscard]] u8 prev(size_t i) const {
        return m_rawData->prev[i];
    }

    [[nodiscard]] u8 next(size_t i) const {
        return m_rawData->next[i];
    }
    /// @endGetters

private:
    const SData *m_rawData;
};

class MapdataItemPathAccessor
    : public MapdataAccessorBase<MapdataItemPath, MapdataItemPath::SData> {
public:
    MapdataItemPathAccessor(const MapSectionHeader *header);
    ~MapdataItemPathAccessor() override;
};

} // namespace Kinoko::System
