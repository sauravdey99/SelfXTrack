idf_component_register(
    SRCS "main.c" "modem.c" "gnss.c" "accel.c" "power.c" "io.c" "ota.c" "ble.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_adc esp_timer nvs_flash json app_update mbedtls bt
)
