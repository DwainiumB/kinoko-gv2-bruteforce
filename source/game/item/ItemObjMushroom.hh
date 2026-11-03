#pragma once

#include "game/item/ItemObj.hh"

namespace Kinoko::Item {

/// @brief The mushroom (vtable 0x808D1FB0). It only lies on the course after being dropped (by a
/// hit kart or a broken course object), and a kart that touches it gets a mushroom boost. It has
/// no state function of its own and no callbacks other than its model.
class ItemObjMushroom : public ItemObj {
public:
    ItemObjMushroom();
    ~ItemObjMushroom() override;

protected:
    [[nodiscard]] StateFunc initialState() const override;
};

/// @brief The star (vtable 0x808D2698). Like the mushroom: a kart that touches a dropped one
/// gets a star.
class ItemObjStar : public ItemObj {
public:
    ItemObjStar();
    ~ItemObjStar() override;

protected:
    [[nodiscard]] StateFunc initialState() const override;
};

} // namespace Kinoko::Item
