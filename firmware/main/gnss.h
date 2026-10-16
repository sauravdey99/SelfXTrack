#pragma once
#include <stdbool.h>
typedef struct {
    bool valid;
    double lat, lon;
    float hdop, speed_kmh, heading;
    int sats;
} gnss_fix_t;

bool gnss_start(void);
bool gnss_get_fix(gnss_fix_t *fix, int timeout_s);
void gnss_stop(void);
