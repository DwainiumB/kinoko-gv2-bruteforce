#include "MapdataItemPath.hh"

namespace Kinoko::System {

MapdataItemPath::MapdataItemPath(const SData *data) : m_rawData(data) {}

/// @addr{Inlined at 0x80513BFC}
MapdataItemPathAccessor::MapdataItemPathAccessor(const MapSectionHeader *header)
    : MapdataAccessorBase<MapdataItemPath, MapdataItemPath::SData>(header) {
    init(reinterpret_cast<const MapdataItemPath::SData *>(m_sectionHeader + 1),
            parse<u16>(m_sectionHeader->count));
}

MapdataItemPathAccessor::~MapdataItemPathAccessor() = default;

} // namespace Kinoko::System
