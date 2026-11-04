#pragma once

#include "game/field/ObjectCollisionBase.hh"

namespace Kinoko::Field {

/// @brief A point with a bounding radius, the collider the game builds for an item when it tests
/// it against a convex shape: the item-vs-kart hull test keeps one at 0x809C3628 (vtable
/// 0x808D198C), the item-vs-object search one inside the ObjectDirector (+0x134, vtable
/// 0x808D7FF8). Both classes behave the same: the support point is always the centre.
class ObjectCollisionPoint : public ObjectCollisionBase {
public:
    ObjectCollisionPoint() : m_radius(0.0f) {}
    ~ObjectCollisionPoint() override = default;

    /// @brief The search writes the two fields directly (director +0x150 and +0x154).
    void set(f32 radius, const EGG::Vector3f &pos) {
        m_radius = radius;
        m_pos = pos;
    }

    /// @addr{0x8082B52C}
    void transform(const EGG::Matrix34f & /*mat*/, const EGG::Vector3f & /*scale*/) override {}

    /// @addr{0x8082B530}
    void transform(const EGG::Matrix34f & /*mat*/, const EGG::Vector3f & /*scale*/,
            const EGG::Vector3f & /*speed*/) override {}

    /// @addr{0x8082B534}
    const EGG::Vector3f &getSupport(const EGG::Vector3f & /*v*/) const override {
        return m_pos;
    }

    /// @addr{0x8082B524}
    f32 getBoundingRadius() const override {
        return m_radius;
    }

private:
    f32 m_radius;        ///< +0x1C
    EGG::Vector3f m_pos; ///< +0x20
};

} // namespace Kinoko::Field
