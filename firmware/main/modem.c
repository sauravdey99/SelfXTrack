// Quectel EG800K AT-command driver (UART1, 1.8 V side through TXS0108E).
// IMPORTANT: verify timings and HTTP/SSL commands against the EG800K Hardware Design guide
// and "Quectel LTE Standard HTTP(S) Application Note" before production.
#include "modem.h"
#include "board.h"
#include <stdio.h>
#include <string.h>
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "ca_cert.h"

static const char *TAG = "modem";
static bool s_ca_uploaded;          // root CA copied to the modem since power-on
#define RXBUF 2048

static int64_t now_ms(void) { return esp_timer_get_time() / 1000; }

void modem_init(void) {
    uart_config_t c = {.baud_rate = MODEM_BAUD, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
                       .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
                       .source_clk = UART_SCLK_DEFAULT};
    uart_driver_install(MODEM_UART, RXBUF, 1024, 0, NULL, 0);
    uart_param_config(MODEM_UART, &c);
    uart_set_pin(MODEM_UART, PIN_MODEM_TX, PIN_MODEM_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    gpio_config_t o = {.pin_bit_mask = (1ULL << PIN_MODEM_EN) | (1ULL << PIN_MODEM_PWRKEY) | (1ULL << PIN_MODEM_RESET),
                       .mode = GPIO_MODE_OUTPUT};
    gpio_config(&o);
    gpio_set_level(PIN_MODEM_EN, 0);
    gpio_set_level(PIN_MODEM_PWRKEY, 0);
    gpio_set_level(PIN_MODEM_RESET, 0);
}

static void write_str(const char *s) { uart_write_bytes(MODEM_UART, s, strlen(s)); }

// Read until 'expect' (or ERROR) appears or timeout. Returns true if expect found.
static bool read_until(char *buf, size_t len, const char *expect, int timeout_ms) {
    size_t n = 0;
    int64_t end = now_ms() + timeout_ms;
    buf[0] = 0;
    while (now_ms() < end && n < len - 1) {
        int r = uart_read_bytes(MODEM_UART, (uint8_t *)buf + n, len - 1 - n, pdMS_TO_TICKS(50));
        if (r > 0) {
            n += r; buf[n] = 0;
            if (expect && strstr(buf, expect)) return true;
            if (strstr(buf, "ERROR")) return false;
        }
    }
    return expect ? strstr(buf, expect) != NULL : true;
}

bool modem_cmd_resp(const char *cmd, char *resp, size_t len, int timeout_ms) {
    uart_flush_input(MODEM_UART);
    write_str(cmd); write_str("\r");
    bool ok = read_until(resp, len, "OK", timeout_ms);
    ESP_LOGD(TAG, "%s -> %s", cmd, resp);
    return ok;
}

bool modem_cmd(const char *cmd, const char *expect, int timeout_ms) {
    char r[256];
    uart_flush_input(MODEM_UART);
    write_str(cmd); write_str("\r");
    return read_until(r, sizeof(r), expect, timeout_ms);
}

bool modem_power_on(void) {
    s_ca_uploaded = false;
    gpio_set_level(PIN_MODEM_EN, 1);           // load switch on (battery -> VBAT)
    vTaskDelay(pdMS_TO_TICKS(100));
    gpio_set_level(PIN_MODEM_PWRKEY, 1);       // pull PWRKEY low via transistor
    vTaskDelay(pdMS_TO_TICKS(800));            // check EG800K datasheet (typ. >= 500 ms)
    gpio_set_level(PIN_MODEM_PWRKEY, 0);
    for (int i = 0; i < 20; i++) {             // wait for AT ready (up to ~10 s)
        vTaskDelay(pdMS_TO_TICKS(500));
        if (modem_cmd("AT", "OK", 300)) {
            modem_cmd("ATE0", "OK", 500);      // echo off
            modem_cmd("AT+CMEE=2", "OK", 500);
            ESP_LOGI(TAG, "modem ready");
            return true;
        }
    }
    ESP_LOGE(TAG, "modem did not respond");
    return false;
}

void modem_power_off(void) {
    modem_cmd("AT+QPOWD=1", "POWERED DOWN", 5000);
    gpio_set_level(PIN_MODEM_EN, 0);           // cut power completely (lowest sleep current)
}

bool modem_wait_network(int timeout_s) {
    char r[128];
    for (int i = 0; i < timeout_s; i++) {
        if (modem_cmd_resp("AT+CEREG?", r, sizeof(r), 500) && (strstr(r, ",1") || strstr(r, ",5"))) return true;
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    return false;
}

bool modem_data_up(const char *apn) {
    char cmd[96];
    snprintf(cmd, sizeof(cmd), "AT+QICSGP=1,1,\"%s\",\"\",\"\",1", apn);
    modem_cmd(cmd, "OK", 1000);
    if (modem_cmd("AT+QIACT?", "+QIACT: 1,1", 1000)) return true;
    return modem_cmd("AT+QIACT=1", "OK", 30000);
}

int modem_rssi_dbm(void) {
    char r[64]; int rssi = 99, ber;
    if (modem_cmd_resp("AT+CSQ", r, sizeof(r), 500)) {
        const char *p = strstr(r, "+CSQ:");
        if (p) sscanf(p, "+CSQ: %d,%d", &rssi, &ber);
    }
    return rssi == 99 ? 0 : -113 + 2 * rssi;
}

// ---- HTTPS: verify the server certificate (seclevel 1) against our root CA.
// Without this anyone on the network path could pretend to be the server (fake commands / firmware).
// NOTE: AT+QFUPL / AT+QSSLCFG syntax follows the Quectel SSL & FILE application notes – verify on the EG800K.
static bool ssl_setup(const char *url) {
    if (strncmp(url, "https", 5) != 0) return true;
    if (!s_ca_uploaded) {
        char cmd[80], r[96];
        size_t n = strlen(SX_CA_CERT_PEM);
        modem_cmd("AT+QFDEL=\"UFS:cacert.pem\"", "OK", 2000);           // ignore error if it does not exist
        snprintf(cmd, sizeof(cmd), "AT+QFUPL=\"UFS:cacert.pem\",%d,100\r", (int)n);
        uart_flush_input(MODEM_UART); write_str(cmd);
        if (!read_until(r, sizeof(r), "CONNECT", 5000)) { ESP_LOGE(TAG, "CA upload refused"); return false; }
        uart_write_bytes(MODEM_UART, SX_CA_CERT_PEM, n);
        if (!read_until(r, sizeof(r), "+QFUPL:", 10000)) { ESP_LOGE(TAG, "CA upload failed"); return false; }
        s_ca_uploaded = true;
    }
    modem_cmd("AT+QHTTPCFG=\"sslctxid\",1", "OK", 1000);
    modem_cmd("AT+QSSLCFG=\"sslversion\",1,4", "OK", 1000);              // TLS 1.0–1.2 negotiated, server picks 1.2
    modem_cmd("AT+QSSLCFG=\"ciphersuite\",1,0xFFFF", "OK", 1000);
    modem_cmd("AT+QSSLCFG=\"cacert\",1,\"UFS:cacert.pem\"", "OK", 1000);
    modem_cmd("AT+QSSLCFG=\"sni\",1,1", "OK", 1000);
    // seclevel 1 = verify the server against cacert. Refuse to talk if this cannot be set.
    return modem_cmd("AT+QSSLCFG=\"seclevel\",1,1", "OK", 1000);
}

static bool send_data_after_connect(const char *data, int timeout_ms) {
    char r[128];
    if (!read_until(r, sizeof(r), "CONNECT", timeout_ms)) return false;
    write_str(data);
    return read_until(r, sizeof(r), "OK", timeout_ms);
}

int modem_http_post(const char *url, const char *extra_headers, const char *json, char *resp, size_t resp_len) {
    char cmd[64], buf[512], host[96] = {0}, path[160] = {0};
    // split URL into host + path for the raw request header
    const char *h = strstr(url, "://"); h = h ? h + 3 : url;
    const char *slash = strchr(h, '/');
    snprintf(host, sizeof(host), "%.*s", slash ? (int)(slash - h) : (int)strlen(h), h);
    snprintf(path, sizeof(path), "%s", slash ? slash : "/");

    modem_cmd("AT+QHTTPCFG=\"contextid\",1", "OK", 1000);
    modem_cmd("AT+QHTTPCFG=\"requestheader\",1", "OK", 1000);
    if (!ssl_setup(url)) return -1;
    snprintf(cmd, sizeof(cmd), "AT+QHTTPURL=%d,80\r", (int)strlen(url));
    uart_flush_input(MODEM_UART); write_str(cmd);
    if (!send_data_after_connect(url, 5000)) return -1;

    char req[1024];
    int n = snprintf(req, sizeof(req),
                     "POST %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\n%sContent-Length: %d\r\n\r\n%s",
                     path, host, extra_headers ? extra_headers : "", (int)strlen(json), json);
    snprintf(cmd, sizeof(cmd), "AT+QHTTPPOST=%d,60,60\r", n);
    uart_flush_input(MODEM_UART); write_str(cmd);
    if (!send_data_after_connect(req, 10000)) return -1;
    if (!read_until(buf, sizeof(buf), "+QHTTPPOST:", 60000)) return -1;
    int err = -1, code = -1, len = 0;
    sscanf(strstr(buf, "+QHTTPPOST:"), "+QHTTPPOST: %d,%d,%d", &err, &code, &len);
    if (err != 0) return -1;

    if (resp && resp_len) {
        resp[0] = 0;
        uart_flush_input(MODEM_UART); write_str("AT+QHTTPREAD=30\r");
        char rb[768];
        if (read_until(rb, sizeof(rb), "+QHTTPREAD:", 30000)) {
            char *b = strstr(rb, "CONNECT");
            if (b) { b = strchr(b, '\n'); if (b) snprintf(resp, resp_len, "%s", b + 1); }
        }
    }
    return code;
}

bool modem_send_sms(const char *number, const char *text) {
    char cmd[64], r[128];
    if (!number || !number[0]) return false;
    modem_cmd("AT+CMGF=1", "OK", 1000);
    snprintf(cmd, sizeof(cmd), "AT+CMGS=\"%s\"\r", number);
    uart_flush_input(MODEM_UART); write_str(cmd);
    if (!read_until(r, sizeof(r), ">", 5000)) return false;
    write_str(text);
    uart_write_bytes(MODEM_UART, "\x1A", 1);   // Ctrl-Z
    return read_until(r, sizeof(r), "+CMGS:", 30000);
}


// ---- Phase 5: OTA download in chunks (resumable over a weak 4G link).
// NOTE/TODO: verify AT+QHTTPGET with custom request header + AT+QHTTPREAD binary framing on the EG800K.
int modem_http_get_range(const char *url, const char *extra_headers, int from, int len, uint8_t *out) {
    char cmd[64], buf[256], host[96] = {0}, path[160] = {0};
    const char *h = strstr(url, "://"); h = h ? h + 3 : url;
    const char *slash = strchr(h, '/');
    snprintf(host, sizeof(host), "%.*s", slash ? (int)(slash - h) : (int)strlen(h), h);
    snprintf(path, sizeof(path), "%s", slash ? slash : "/");
    modem_cmd("AT+QHTTPCFG=\"contextid\",1", "OK", 1000);
    modem_cmd("AT+QHTTPCFG=\"requestheader\",1", "OK", 1000);
    if (!ssl_setup(url)) return -1;                                       // firmware downloads: verified HTTPS only
    snprintf(cmd, sizeof(cmd), "AT+QHTTPURL=%d,80\r", (int)strlen(url));
    uart_flush_input(MODEM_UART); write_str(cmd);
    if (!send_data_after_connect(url, 5000)) return -1;
    char req[512];
    int n = snprintf(req, sizeof(req), "GET %s HTTP/1.1\r\nHost: %s\r\n%sRange: bytes=%d-%d\r\n\r\n",
                     path, host, extra_headers ? extra_headers : "", from, from + len - 1);
    snprintf(cmd, sizeof(cmd), "AT+QHTTPGET=60,%d\r", n);
    uart_flush_input(MODEM_UART); write_str(cmd);
    if (!send_data_after_connect(req, 10000)) return -1;
    if (!read_until(buf, sizeof(buf), "+QHTTPGET:", 60000)) return -1;
    int err = -1, code = -1, clen = 0;
    sscanf(strstr(buf, "+QHTTPGET:"), "+QHTTPGET: %d,%d,%d", &err, &code, &clen);
    if (err != 0 || (code != 206 && code != 200)) return -1;
    uart_flush_input(MODEM_UART); write_str("AT+QHTTPREAD=60\r");
    if (!read_until(buf, sizeof(buf), "CONNECT\r\n", 10000)) return -1;
    int got = 0;
    while (got < clen && got < len) {
        int r = uart_read_bytes(MODEM_UART, out + got, (clen < len ? clen : len) - got, pdMS_TO_TICKS(5000));
        if (r <= 0) break;
        got += r;
    }
    read_until(buf, sizeof(buf), "+QHTTPREAD:", 5000);
    return got;
}
