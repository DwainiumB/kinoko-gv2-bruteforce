#pragma once

namespace Kinoko::Host {

/// @brief `kinoko_host item-anchors <Race/Kart directory> <output file>`: reads every
/// `<vehicle>-<character>.szs` kart archive from the player's own game files, computes the two
/// driver item anchors from each `driver_model.brres`, and writes the table Kinoko loads from
/// `Race/Kart/driverItemAnchors.bin`. The archives themselves are not copied anywhere.
/// @return true when at least one entry was written.
bool GenerateDriverItemAnchors(const char *kartDir, const char *outPath);

} // namespace Kinoko::Host
