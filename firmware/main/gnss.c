// GNSS through the EG800K integrated receiver (Quectel AT commands).
// NOTE: verify command names/format against "Quectel EG800K GNSS Application Note"
// (AT+QGPS / AT+QGPSLOC are used on most Quectel LTE modules).
#include "gnss.h"
#include "modem.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

bool gnss_start(void) { return modem_cmd("AT+QGPS=1", "OK", 2000) || modem_cmd("AT+QGPS?", "+QGPS: 1", 1000); }
void gnss_stop(void) { modem_cmd("AT+QGPSEND", "OK", 2000); }

// +QGPSLOC: <UTC>,<lat>,<lon>,<hdop>,<alt>,<fix>,<cog>,<spkm>,<spkn>,<date>,<nsat>   (mode 2: decimal degrees)
static bool parse(const char *r, gnss_fix_t *f) {
    const char *p = strstr(r, "+QGPSLOC:");
    if (!p) return false;
    p += 9;
    char buf[160];
    strncpy(buf, p, sizeof(buf) - 1); buf[sizeof(buf) - 1] = 0;
    char *tok[12] = {0}; int n = 0;
    for (char *s = strtok(buf, ","); s && n < 12; s = strtok(NULL, ",")) tok[n++] = s;
    if (n < 11) return false;
    f->lat = atof(tok[1]); f->lon = atof(tok[2]); f->hdop = atof(tok[3]);
    f->heading = atof(tok[6]); f->speed_kmh = atof(tok[7]); f->sats = atoi(tok[10]);
    f->valid = true;
    return true;
}

bool gnss_get_fix(gnss_fix_t *fix, int timeout_s) {
    char resp[256];
    memset(fix, 0, sizeof(*fix));
    for (int i = 0; i < timeout_s; i += 2) {
        if (modem_cmd_resp("AT+QGPSLOC=2", resp, sizeof(resp), 1500) && parse(resp, fix)) return true;
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
    return false;
}
