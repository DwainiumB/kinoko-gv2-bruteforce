#include "ItemObjMushroom.hh"

namespace Kinoko::Item {

/// @addr{0x807A6928}
ItemObjMushroom::ItemObjMushroom() = default;

/// @addr{0x807A9D90}
ItemObjMushroom::~ItemObjMushroom() = default;

/// @brief The static property's state function is null (0x807A9DAC).
ItemObj::StateFunc ItemObjMushroom::initialState() const {
    return nullptr;
}

/// @addr{0x807A6928}
ItemObjStar::ItemObjStar() = default;

/// @addr{0x807B70C0}
ItemObjStar::~ItemObjStar() = default;

/// @brief The static property's state function is null (0x807B70DC).
ItemObj::StateFunc ItemObjStar::initialState() const {
    return nullptr;
}

} // namespace Kinoko::Item
