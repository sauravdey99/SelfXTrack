// SelfXTrack firmware - Phases 1-5 (Phase 5: elderly fall detection, bus beacons, OTA updates)
// Wake -> (SOS?) -> modem on -> GNSS fix -> POST telemetry -> obey server interval -> deep sleep.
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "board.h"
#include "io.h"
#include "power.h"
#include "accel.h"
#include "modem.h"
#include "gnss.h"
#include "ota.h"
#include "ble.h"
#include "secrets.h"
#include "cJSON.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "nvs_flash.h"
#include "driver/rtc_io.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "selfx";

// Survive deep sleep
static RTC_DATA_ATTR int  s_interval_s = 300;
static RTC_DATA_ATTR bool s_sos_active = false;
static RTC_DATA_ATTR double s_last_lat = 0, s_last_lon = 0;
static RTC_DATA_ATTR int  s_still_cycles = 0;
// Phase 5 – settings pushed by the server in every reply ("cfg"), kept across deep sleep
static RTC_DATA_ATTR bool s_fall_enabled = false;
static RTC_DATA_ATTR int  s_n_beacons = 0;
static RTC_DATA_ATTR char s_beacons[BLE_MAX_BEACONS][24];
static RTC_DATA_ATTR int  s_motion = 0;         // motion wake-ups since the last report (elderly inactivity)
static char s_ota_ver[32], s_ota_url[192], s_ota_sha[65];
static int  s_ota_size = 0;

#define FALL_CANCEL_S        30     // wearer can cancel a fall alert with the SOS button

#define SOS_HOLD_MS          1500   // hold to trigger (avoids accidental presses)
#define STATIONARY_SLEEP_S   1800   // heartbeat when not moving
#define GNSS_TIMEOUT_S       60
#define GNSS_TIMEOUT_SOS_S   20

static bool check_sos_hold(void) {
    int held = 0;
    while (io_sos_pressed() && held < SOS_HOLD_MS) { vTaskDelay(pdMS_TO_TICKS(50)); held += 50; }
    return held >= SOS_HOLD_MS;
}

static void send_sos_sms(void) {
    char text[160];
    if (s_last_lat != 0)
        snprintf(text, sizeof(text), "SOS %s! Last location: https://maps.google.com/?q=%.6f,%.6f", SX_DEVICE_ID,
                 s_last_lat, s_last_lon);
    else
        snprintf(text, sizeof(text), "SOS %s! Location not available yet.", SX_DEVICE_ID);
    modem_send_sms(SX_SOS_SMS_1, text);
    modem_send_sms(SX_SOS_SMS_2, text);
}

// Fall: free-fall + impact -> vibrate for 30 s; pressing the SOS button cancels. Returns true = send fall alert.
static bool fall_confirmed(void) {
    if (!accel_impact_after(1500)) return false;          // free-fall without impact (e.g. dropped on bed)
    ESP_LOGW(TAG, "possible fall - %d s to cancel", FALL_CANCEL_S);
    for (int t = 0; t < FALL_CANCEL_S * 10; t++) {
        if (t % 20 == 0) io_buzz(300);                     // vibrate/beep every 2 s
        if (io_sos_pressed()) { io_buzz(60); ESP_LOGI(TAG, "fall cancelled by wearer"); return false; }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    return true;
}

static void parse_cfg(cJSON *r) {
    cJSON *cfg = cJSON_GetObjectItem(r, "cfg");
    if (cJSON_IsObject(cfg)) {
        cJSON *f = cJSON_GetObjectItem(cfg, "fall"), *b = cJSON_GetObjectItem(cfg, "beacons");
        bool want = cJSON_IsTrue(f);
        if (want != s_fall_enabled) { s_fall_enabled = want; accel_enable_fall(want); }
        s_n_beacons = 0;
        cJSON *it;
        cJSON_ArrayForEach(it, b) {
            if (cJSON_IsString(it) && s_n_beacons < BLE_MAX_BEACONS)
                snprintf(s_beacons[s_n_beacons++], 24, "%s", it->valuestring);
        }
    }
    cJSON *o = cJSON_GetObjectItem(r, "ota");
    s_ota_size = 0;
    if (cJSON_IsObject(o)) {
        cJSON *v = cJSON_GetObjectItem(o, "version"), *u = cJSON_GetObjectItem(o, "url"),
              *h = cJSON_GetObjectItem(o, "sha256"), *z = cJSON_GetObjectItem(o, "size");
        if (cJSON_IsString(v) && cJSON_IsString(u) && cJSON_IsString(h) && cJSON_IsNumber(z)) {
            snprintf(s_ota_ver, sizeof(s_ota_ver), "%s", v->valuestring);
            snprintf(s_ota_url, sizeof(s_ota_url), "%s", u->valuestring);
            snprintf(s_ota_sha, sizeof(s_ota_sha), "%s", h->valuestring);
            s_ota_size = z->valueint;
        }
    }
}

static bool report_ex(bool sos, bool fall);
static bool report(bool sos) { return report_ex(sos, false); }

static bool report_ex(bool sos, bool fall) {
    gnss_fix_t fix = {0};
    gnss_get_fix(&fix, sos ? GNSS_TIMEOUT_SOS_S : GNSS_TIMEOUT_S);
    if (fix.valid) { s_last_lat = fix.lat; s_last_lon = fix.lon; }

    cJSON *j = cJSON_CreateObject();
    if (fix.valid) {
        cJSON_AddNumberToObject(j, "lat", fix.lat);
        cJSON_AddNumberToObject(j, "lon", fix.lon);
        cJSON_AddNumberToObject(j, "acc", fix.hdop * 5.0);   // rough metres estimate
        cJSON_AddNumberToObject(j, "spd", fix.speed_kmh);
        cJSON_AddNumberToObject(j, "hdg", fix.heading);
    }
    cJSON_AddNumberToObject(j, "bat", power_battery_percent());
    cJSON_AddNumberToObject(j, "chg", power_charging() ? 1 : 0);
    cJSON_AddNumberToObject(j, "sos", sos ? 1 : 0);
    cJSON_AddStringToObject(j, "fw", SX_FW_VERSION);
    if (fall) cJSON_AddNumberToObject(j, "fall", 1);
    cJSON_AddNumberToObject(j, "act", s_motion);
    if (s_n_beacons > 0) {                                   // bus check-in: 3 s BLE scan for our bus beacons
        char found[BLE_MAX_BEACONS][24];
        int n = ble_scan_beacons((const char (*)[24])s_beacons, s_n_beacons, 3, found);
        cJSON *arr = cJSON_AddArrayToObject(j, "ble");
        for (int i = 0; i < n; i++) cJSON_AddItemToArray(arr, cJSON_CreateString(found[i]));
    }
    char *body = cJSON_PrintUnformatted(j);
    cJSON_Delete(j);

    char hdr[192], resp[768] = {0};
    snprintf(hdr, sizeof(hdr), "X-Device-Id: %s\r\nX-Device-Secret: %s\r\n", SX_DEVICE_ID, SX_DEVICE_SECRET);
    int code = modem_http_post(SX_SERVER_URL, hdr, body, resp, sizeof(resp));
    ESP_LOGI(TAG, "POST %s -> %d %s", body, code, resp);
    free(body);

    if (code == 200) {
        cJSON *r = cJSON_Parse(resp);
        if (r) {
            cJSON *iv = cJSON_GetObjectItem(r, "interval_s"), *sa = cJSON_GetObjectItem(r, "sos_active");
            if (cJSON_IsNumber(iv)) s_interval_s = iv->valueint;
            if (cJSON_IsBool(sa)) s_sos_active = cJSON_IsTrue(sa);
            parse_cfg(r);
            cJSON_Delete(r);
        }
        s_motion = 0;
        ota_confirm_if_pending();                           // new firmware reached the server -> keep it
        return true;
    }
    return false;
}

static void go_to_sleep(int seconds) {
    ESP_LOGI(TAG, "sleep %d s", seconds);
    modem_power_off();
    uint64_t mask = (1ULL << PIN_SOS_BTN) | (1ULL << PIN_ACC_INT1);
    if (s_fall_enabled) mask |= (1ULL << PIN_ACC_INT2);      // free-fall wakes us (elderly mode)
    rtc_gpio_pullup_en(PIN_SOS_BTN);
    esp_sleep_enable_ext1_wakeup(mask, ESP_EXT1_WAKEUP_ANY_LOW);
    esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
    esp_deep_sleep_start();
}

void app_main(void) {
    nvs_flash_init();
    io_init();
    power_init();
    bool accel_ok = accel_init();
    modem_init();

    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    bool sos = false;
    if (cause == ESP_SLEEP_WAKEUP_EXT1 && io_sos_pressed() && check_sos_hold()) sos = true;
    if (cause == ESP_SLEEP_WAKEUP_UNDEFINED) io_buzz(80);           // first boot beep
    if (sos) { io_sos_feedback(); s_sos_active = true; }

    // Phase 5: fall detection (elderly mode) – woken by free-fall on INT2
    bool fall = false;
    if (accel_ok && s_fall_enabled && accel_fall_event()) fall = fall_confirmed();

    bool moving = accel_ok ? accel_moving() : true;
    if (moving) s_motion++;
    s_still_cycles = moving ? 0 : s_still_cycles + 1;

    io_led(true);
    bool ok = modem_power_on() && modem_wait_network(sos ? 60 : 90) && modem_data_up(SX_APN);
    gnss_start();

    int rounds = 0;
    do {
        bool sent = ok && report_ex(sos || s_sos_active, fall && rounds == 0);
        if (fall && !sent && rounds == 0) send_sos_sms();                     // fall + no data -> SMS
        if (!sent && (sos || s_sos_active) && rounds == 0) send_sos_sms();   // fallback when data fails
        if (!s_sos_active) break;
        // SOS mode: stay awake and report fast until family marks the child safe (server clears it)
        vTaskDelay(pdMS_TO_TICKS(s_interval_s * 1000));
        if (io_sos_pressed() && check_sos_hold()) io_sos_feedback();
        sos = false;
    } while (++rounds < 360);   // safety limit (~1 h at 10 s) then normal cycle continues

    // Phase 5: install a firmware update the server offered (never during SOS; server also checks battery)
    if (ok && !s_sos_active && s_ota_size > 0) { gnss_stop(); ota_run(s_ota_ver, s_ota_url, s_ota_sha, s_ota_size); }

    gnss_stop();
    io_led(false);
    int sleep_s = s_interval_s;
    if (!s_sos_active && s_still_cycles >= 2) sleep_s = STATIONARY_SLEEP_S;  // not moving: save battery
    go_to_sleep(sleep_s);
}
