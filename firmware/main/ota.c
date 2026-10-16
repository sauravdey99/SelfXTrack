// Phase 5: OTA firmware updates over 4G (EG800K AT HTTP, ranged chunks -> esp_ota_*).
// Safety: only offered by the server when no SOS is active and battery >= 30 % (or charging).
// A new image must report to the server once, otherwise the bootloader rolls back on the next reset.
#include "ota.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "modem.h"
#include "secrets.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "mbedtls/sha256.h"
#include "cJSON.h"

static const char *TAG = "ota";
#define CHUNK 4096

static void report_status(const char *version, const char *status) {
    char url[192], hdr[192], body[128], resp[64];
    // SX_SERVER_URL ends with /api/device/telemetry -> same base, /ota-status
    snprintf(url, sizeof(url), "%s", SX_SERVER_URL);
    char *p = strstr(url, "/telemetry");
    if (p) strcpy(p, "/ota-status");
    snprintf(hdr, sizeof(hdr), "X-Device-Id: %s\r\nX-Device-Secret: %s\r\n", SX_DEVICE_ID, SX_DEVICE_SECRET);
    snprintf(body, sizeof(body), "{\"version\":\"%s\",\"status\":\"%s\"}", version, status);
    modem_http_post(url, hdr, body, resp, sizeof(resp));
}

bool ota_run(const char *version, const char *url, const char *sha256_hex, int size) {
    const esp_partition_t *part = esp_ota_get_next_update_partition(NULL);
    if (!part || size <= 0 || size > (int)part->size) { ESP_LOGE(TAG, "no partition / bad size"); return false; }
    esp_ota_handle_t h;
    if (esp_ota_begin(part, size, &h) != ESP_OK) return false;
    report_status(version, "downloading");

    char hdr[192];
    snprintf(hdr, sizeof(hdr), "X-Device-Id: %s\r\nX-Device-Secret: %s\r\n", SX_DEVICE_ID, SX_DEVICE_SECRET);
    uint8_t *buf = malloc(CHUNK);
    mbedtls_sha256_context sha;
    mbedtls_sha256_init(&sha);
    mbedtls_sha256_starts(&sha, 0);
    int done = 0, retries = 0;
    while (done < size && buf) {
        int want = size - done < CHUNK ? size - done : CHUNK;
        int got = modem_http_get_range(url, hdr, done, want, buf);
        if (got != want) {
            if (++retries > 5) break;          // weak signal: retry the same chunk
            continue;
        }
        retries = 0;
        mbedtls_sha256_update(&sha, buf, got);
        if (esp_ota_write(h, buf, got) != ESP_OK) break;
        done += got;
    }
    free(buf);
    uint8_t digest[32];
    char hex[65];
    mbedtls_sha256_finish(&sha, digest);
    mbedtls_sha256_free(&sha);
    for (int i = 0; i < 32; i++) sprintf(hex + i * 2, "%02x", digest[i]);

    if (done != size) { esp_ota_abort(h); report_status(version, "failed:download"); return false; }
    if (strcasecmp(hex, sha256_hex) != 0) { esp_ota_abort(h); report_status(version, "failed:sha256"); return false; }
    if (esp_ota_end(h) != ESP_OK || esp_ota_set_boot_partition(part) != ESP_OK) {
        report_status(version, "failed:install"); return false;
    }
    report_status(version, "installed");
    ESP_LOGI(TAG, "update %s installed, rebooting", version);
    modem_power_off();
    esp_restart();
    return true;
}

void ota_confirm_if_pending(void) {
    esp_ota_img_states_t st;
    const esp_partition_t *run = esp_ota_get_running_partition();
    if (esp_ota_get_state_partition(run, &st) == ESP_OK && st == ESP_OTA_IMG_PENDING_VERIFY) {
        esp_ota_mark_app_valid_cancel_rollback();   // reached the server on the new image -> keep it
        ESP_LOGI(TAG, "new firmware confirmed");
    }
}
