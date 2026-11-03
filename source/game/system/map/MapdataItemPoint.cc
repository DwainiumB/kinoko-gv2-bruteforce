#include "MapdataItemPoint.hh"

#include "game/system/CourseMap.hh"
#include "game/system/map/MapdataItemPath.hh"

namespace Kinoko::System {

MapdataItemPoint::MapdataItemPoint(const SData *data)
    : m_rawData(data), m_prevCount(0), m_nextCount(0) {
    m_prev.fill(NONE);
    m_next.fill(NONE);
    EGG::RamStream stream = EGG::RamStream(data, sizeof(SData));
    read(stream);
}

void MapdataItemPoint::read(EGG::Stream &stream) {
    m_pos.read(stream);
    m_deviation = stream.read_f32();
    m_setting1 = stream.read_u16();
    m_setting2 = stream.read_u16();
}

/// @addr{0x80517E88}
/// @brief Inside a path a point links to its neighbours; the first and last points of a path link
/// to the last and first points of the paths before and after it.
void MapdataItemPoint::initLinks(u8 idx) {
    m_prevCount = 0;
    m_nextCount = 0;
    m_prev.fill(NONE);
    m_next.fill(NONE);

    auto *courseMap = CourseMap::Instance();
    u16 pathCount = courseMap->getItemPathCount();
    for (u16 i = 0; i < pathCount; ++i) {
        const MapdataItemPath *path = courseMap->getItemPath(i);
        if (idx < path->start() || idx > path->end()) {
            continue;
        }

        if (idx == path->start()) {
            for (size_t j = 0; j < MapdataItemPath::MAX_NEIGHBORS; ++j) {
                u8 other = path->prev(j);
                if (other != NONE) {
                    m_prev[m_prevCount++] = courseMap->getItemPath(other)->end();
                }
            }
        } else if (m_prevCount == 0) {
            m_prev[m_prevCount++] = idx - 1;
        }

        if (idx == path->end()) {
            for (size_t j = 0; j < MapdataItemPath::MAX_NEIGHBORS; ++j) {
                u8 other = path->next(j);
                if (other != NONE) {
                    m_next[m_nextCount++] = courseMap->getItemPath(other)->start();
                }
            }
        } else if (m_nextCount == 0) {
            m_next[m_nextCount++] = idx + 1;
        }
    }
}

/// @addr{Inlined at 0x80513ADC}
MapdataItemPointAccessor::MapdataItemPointAccessor(const MapSectionHeader *header)
    : MapdataAccessorBase<MapdataItemPoint, MapdataItemPoint::SData>(header) {
    init(reinterpret_cast<const MapdataItemPoint::SData *>(m_sectionHeader + 1),
            parse<u16>(m_sectionHeader->count));
}

MapdataItemPointAccessor::~MapdataItemPointAccessor() = default;

} // namespace Kinoko::System
