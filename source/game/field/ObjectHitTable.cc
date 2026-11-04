#include "ObjectHitTable.hh"

#include "game/system/ResourceManager.hh"

#include <egg/util/Stream.hh>

namespace Kinoko::Field {

/// @addr{0x807F9278}
ObjectHitTable::ObjectHitTable(const char *filename) {
    size_t size;
    void *file =
            System::ResourceManager::Instance()->getFile(filename, &size, System::ArchiveId::Core);

    EGG::RamStream stream = EGG::RamStream(file, size);

    m_count = stream.read_s16();
    m_fieldCount = stream.read_s16();
    m_reactions = owning_span<s16>(m_count * m_fieldCount);

    // The game keeps a pointer per row, just past its header (+0x0C).
    for (s16 i = 0; i < m_count; ++i) {
        stream.skip(0x2);
        for (s16 j = 0; j < m_fieldCount; ++j) {
            m_reactions[i * m_fieldCount + j] = stream.read_s16();
        }
    }

    m_slots = reinterpret_cast<const s16 *>(stream.dataAtIndex());
}

/// @addr{0x807F9348}
ObjectHitTable::~ObjectHitTable() = default;

Kart::Reaction ObjectHitTable::reaction(s16 i) const {
    ASSERT(i != -1);
    ASSERT(i < m_count);
    return static_cast<Kart::Reaction>(m_reactions[i * m_fieldCount]);
}

/// @brief The reaction in `column` of row `i` (an item table read by item object kind, as
/// 0x8082ADBC does).
s16 ObjectHitTable::reaction(s16 i, s16 column) const {
    ASSERT(i != -1);
    ASSERT(i < m_count);
    ASSERT(column < m_fieldCount);
    return m_reactions[i * m_fieldCount + column];
}

s16 ObjectHitTable::slot(ObjectId id) const {
    constexpr size_t SLOT_COUNT = 0x2f4;

    size_t i = static_cast<std::underlying_type_t<ObjectId>>(id);
    return i < SLOT_COUNT ? parse<s16>(m_slots[i]) : -1;
}

} // namespace Kinoko::Field
