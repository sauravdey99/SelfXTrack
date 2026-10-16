#pragma once
#include <stdbool.h>
// Phase 5: school-bus check-in. Scans BLE for `secs` seconds and reports which of the given beacon IDs
// (the beacon's advertised name, e.g. "BUS-12") were seen. Returns the number found (written to `found`).
#define BLE_MAX_BEACONS 4
int ble_scan_beacons(const char ids[][24], int n_ids, int secs, char found[][24]);
