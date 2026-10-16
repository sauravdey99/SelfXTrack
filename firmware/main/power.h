#pragma once
#include <stdbool.h>
void power_init(void);
int  power_battery_mv(void);
int  power_battery_percent(void);
bool power_usb_present(void);
bool power_charging(void);
