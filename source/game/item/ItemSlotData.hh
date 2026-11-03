#pragma once

#include "game/item/ItemId.hh"

#include <egg/core/Disposer.hh>
#include <egg/core/Heap.hh>

#include <array>

namespace Kinoko {

namespace Host {

class Context;

} // namespace Host

namespace Item {

class KartItem;
enum class ItemObjKind;

/// @addr{0x809C3670}
/// @brief The item odds (the game's `ItemSlotData`, 0x48 bytes): chance tables per place read
/// from ItemSlot.bin, the lists the roulette shows, and the cooldowns of the strong items.
/// @details ItemSlot.bin (Common.szs, or ItemSlotTable/ItemSlotTable.slt in the course archive)
/// starts with a section count. Each section is a rank count, an item count (19) and one byte per
/// item and rank, item-major. Sections: 0/1 Grand Prix players/CPUs, 2/3 VS players/CPUs (3 is
/// also the online CPU one), 4 online players, 5 special boxes (one row per box setting), 6..11
/// battle.
/// @nosubgrouping
class ItemSlotData : EGG::Disposer {
    friend class Host::Context;

public:
    static constexpr size_t ITEM_COUNT = 19;
    static constexpr size_t MAX_RANKS = 12;

    [[nodiscard]] ItemId decideItem(u16 boxSetting, u8 rank, bool human, bool noTriples,
            const KartItem *kartItem);
    [[nodiscard]] ItemId pickShownItem(u16 boxSetting, u8 rank, ItemId current, bool byRank);
    void calcTimers();

    /// @addr{0x807BB9BC}
    void resetLightningTimer() {
        m_lightningTimer = LIGHTNING_COOLDOWN;
    }

    /// @addr{0x807BB9C8}
    void resetBlueShellTimer() {
        m_blueShellTimer = BLUE_SHELL_COOLDOWN;
    }

    /// @addr{0x807BB9D4}
    void resetBlooperTimer() {
        m_blooperTimer = BLOOPER_COOLDOWN;
    }

    /// @addr{0x807BB9E0}
    void resetPowTimer() {
        m_powTimer = POW_COOLDOWN;
    }

    static ItemSlotData *CreateInstance();
    static void DestroyInstance();

    [[nodiscard]] static ItemSlotData *Instance() {
        return s_instance;
    }

private:
    /// @brief One chance table: a row of 19 chances per rank (or per box setting).
    struct Table {
        u32 rowCount;
        u16 *chances; ///< rowCount rows of ITEM_COUNT.
    };

    /// @brief Items with a non-zero chance, without repeats (0x50 bytes in the game).
    struct ItemList {
        void add(ItemId id);

        u32 count;
        std::array<ItemId, ITEM_COUNT> items;
    };

    EGG_NEW_DELETE_FRIEND

    ItemSlotData();
    ~ItemSlotData() override;

    void load();
    [[nodiscard]] const u8 *parseTable(const u8 *data, Table &table, bool fillLists, bool raw);
    void scaleTableForPlayerCount(Table &table);
    [[nodiscard]] s32 cooldown(ItemObjKind kind) const;

    [[nodiscard]] static const u8 *SkipTable(const u8 *data);

    Table m_humanTable;                             ///< +0x10
    Table m_cpuTable;                               ///< +0x18
    Table m_specialTable;                           ///< +0x20 Raw chances per box setting.
    ItemList m_shownItems;                          ///< +0x28 Every item of the player table.
    std::array<ItemList, MAX_RANKS> m_rankItems;    ///< +0x2C The player table's items per rank.
    ItemList *m_specialItems;                       ///< +0x30 The special table's items per row.
    s32 m_lightningTimer;                           ///< +0x34
    s32 m_blueShellTimer;                           ///< +0x38
    s32 m_blooperTimer;                             ///< +0x3C
    s32 m_powTimer;                                 ///< +0x40
    u32 m_playerCount;                              ///< +0x44
    std::array<u16, ITEM_COUNT> m_cumulativeChance; ///< 0x809C3674

    static constexpr s32 LIGHTNING_COOLDOWN = 1800;
    static constexpr s32 BLUE_SHELL_COOLDOWN = 1800;
    static constexpr s32 BLOOPER_COOLDOWN = 900;
    static constexpr s32 POW_COOLDOWN = 1200;

    static ItemSlotData *s_instance; ///< @addr{0x809C3670}
};

} // namespace Item

} // namespace Kinoko
