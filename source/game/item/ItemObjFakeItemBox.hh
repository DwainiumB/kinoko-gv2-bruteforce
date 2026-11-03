#pragma once

#include "game/item/ItemObjBanana.hh"

namespace Kinoko::Item {

/// @brief The fake item box (vtable 0x808D1D60): dropped behind the kart or thrown forward, then
/// lies on the course like a banana. Its spawn, model and break callbacks are visual, and its
/// thrown callback (+0x30) only runs for online objects.
class ItemObjFakeItemBox : public ItemObjThrowable {
public:
    ItemObjFakeItemBox();
    ~ItemObjFakeItemBox() override;

protected:
    [[nodiscard]] bool onRelease(ItemTrail &trail) override;
    [[nodiscard]] StateFunc initialState() const override;

private:
    void calcFakeItemBox();
};

} // namespace Kinoko::Item
