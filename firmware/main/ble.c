// Phase 5: BLE scan for school-bus beacons (NimBLE, observer only – no connections, short scan to save battery).
// Bus beacons advertise their ID as the Complete Local Name (e.g. "BUS-12").
// NOTE/TODO: test with the chosen beacon model; enable CONFIG_BT_ENABLED + CONFIG_BT_NIMBLE_ENABLED (sdkconfig.defaults).
#include "ble.h"
#include <string.h>
#include "esp_log.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "ble";
static const char (*s_ids)[24];
static int s_n, s_found_n;
static char (*s_found)[24];
static SemaphoreHandle_t s_done, s_synced;

static int on_gap(struct ble_gap_event *ev, void *arg) {
    if (ev->type == BLE_GAP_EVENT_DISC) {
        struct ble_hs_adv_fields f;
        if (ble_hs_adv_parse_fields(&f, ev->disc.data, ev->disc.length_data) == 0 && f.name && f.name_len < 24) {
            char name[24] = {0};
            memcpy(name, f.name, f.name_len);
            for (int i = 0; i < s_n; i++) {
                if (strcasecmp(name, s_ids[i]) == 0) {
                    bool dup = false;
                    for (int k = 0; k < s_found_n; k++) dup |= strcasecmp(s_found[k], name) == 0;
                    if (!dup && s_found_n < BLE_MAX_BEACONS) strcpy(s_found[s_found_n++], s_ids[i]);
                }
            }
        }
    } else if (ev->type == BLE_GAP_EVENT_DISC_COMPLETE) {
        xSemaphoreGive(s_done);
    }
    return 0;
}

static void on_sync(void) { xSemaphoreGive(s_synced); }
static void host_task(void *p) { nimble_port_run(); nimble_port_freertos_deinit(); }

int ble_scan_beacons(const char ids[][24], int n_ids, int secs, char found[][24]) {
    if (n_ids <= 0) return 0;
    s_ids = ids; s_n = n_ids; s_found = found; s_found_n = 0;
    s_done = xSemaphoreCreateBinary(); s_synced = xSemaphoreCreateBinary();
    if (nimble_port_init() != ESP_OK) { ESP_LOGE(TAG, "nimble init failed"); return 0; }
    ble_hs_cfg.sync_cb = on_sync;
    nimble_port_freertos_init(host_task);
    if (xSemaphoreTake(s_synced, pdMS_TO_TICKS(3000)) == pdTRUE) {
        struct ble_gap_disc_params dp = {.passive = 1, .filter_duplicates = 1, .itvl = 0x50, .window = 0x30};
        if (ble_gap_disc(BLE_OWN_ADDR_PUBLIC, secs * 1000, &dp, on_gap, NULL) == 0)
            xSemaphoreTake(s_done, pdMS_TO_TICKS(secs * 1000 + 1000));
    }
    nimble_port_stop();
    nimble_port_deinit();
    vSemaphoreDelete(s_done); vSemaphoreDelete(s_synced);
    ESP_LOGI(TAG, "beacons found: %d", s_found_n);
    return s_found_n;
}
