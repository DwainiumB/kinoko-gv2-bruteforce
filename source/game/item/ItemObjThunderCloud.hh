#pragma once

#include "game/item/ItemObj.hh"

namespace Kinoko::Item {

/// @brief The thunder cloud (vtable 0x808D2480, `ItemObjKumo`): it hangs over the racer who drew
/// it and strikes them after 600 frames unless they bump it onto another racer first.
/// @details It has no collision radius: its position only follows the carrier for drawing. The
/// online transfer (+0x1C4), the battle team checks and the race statistics are not ported.
/// @nosubgrouping
class ItemObjThunderCloud : public ItemObj {
public:
    ItemObjThunderCloud();
    ~ItemObjThunderCloud() override;

    void passTo(u8 playerIdx);

    /// @beginGetters
    [[nodiscard]] u8 carrier() const {
        return m_carrier;
    }
    /// @endGetters

protected:
    void onSpawn() override;
    [[nodiscard]] StateFunc initialState() const override;

private:
    void calcThunderCloud();
    void handOver(u8 playerIdx);

    u8 m_carrier;      ///< +0x1A0 (the game keeps the carrier's KartItem)
    u8 m_lastCarrier;  ///< +0x1A4 12: none.
    s32 m_passCount;   ///< +0x1A8
    s32 m_passTimer;   ///< +0x1D4 No hand-over while above 0.
    s32 m_strikeTimer; ///< +0x1D8 Strikes the carrier at 600, breaks after 690.
};

} // namespace Kinoko::Item
