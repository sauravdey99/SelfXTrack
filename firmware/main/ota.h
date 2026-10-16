#pragma once
#include <stdbool.h>
// Download + verify (SHA-256) + install a firmware image offered by the server, then reboot.
// Uses the two OTA partitions (CONFIG_PARTITION_TABLE_TWO_OTA) and bootloader rollback.
bool ota_run(const char *version, const char *url, const char *sha256_hex, int size);
void ota_confirm_if_pending(void);   // call after the first successful server report on the new image
