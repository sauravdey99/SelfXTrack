#pragma once
#include <stdbool.h>
bool accel_init(void);           // configure LIS2DW12 low-power + wake-up on INT1
bool accel_moving(void);         // recent motion (reads + clears wake-up source)
void accel_enable_fall(bool on);  // free-fall detection on INT2 (elderly mode)
bool accel_fall_event(void);      // a free-fall was latched since the last call (reads + clears)
bool accel_impact_after(int ms);  // strong impact (> ~2 g) within `ms` after a free-fall -> real fall
