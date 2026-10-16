#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void modem_init(void);
bool modem_power_on(void);
void modem_power_off(void);
bool modem_cmd(const char *cmd, const char *expect, int timeout_ms);
bool modem_cmd_resp(const char *cmd, char *resp, size_t len, int timeout_ms);
bool modem_wait_network(int timeout_s);
bool modem_data_up(const char *apn);
// HTTP POST JSON; returns HTTP status (or -1). Response body copied to resp.
// GET bytes [from, from+len) of a URL into buf (HTTP Range). Returns bytes read, or -1.
int  modem_http_get_range(const char *url, const char *extra_headers, int from, int len, uint8_t *buf);
int  modem_http_post(const char *url, const char *extra_headers, const char *json, char *resp, size_t resp_len);
bool modem_send_sms(const char *number, const char *text);
int  modem_rssi_dbm(void);
