#include "io.h"
#include "board.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void io_init(void) {
    gpio_config_t in = {
        .pin_bit_mask = (1ULL << PIN_SOS_BTN) | (1ULL << PIN_BOOT_BTN),
        .mode = GPIO_MODE_INPUT, .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    gpio_config(&in);
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << PIN_LED) | (1ULL << PIN_BUZZER) | (1ULL << PIN_VIBRATION),
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&out);
    io_led(false);
    gpio_set_level(PIN_BUZZER, 0);
    gpio_set_level(PIN_VIBRATION, 0);
}

bool io_sos_pressed(void) { return gpio_get_level(PIN_SOS_BTN) == 0; }
void io_led(bool on) { gpio_set_level(PIN_LED, on); }

void io_buzz(int ms) {
    gpio_set_level(PIN_BUZZER, 1);
    vTaskDelay(pdMS_TO_TICKS(ms));
    gpio_set_level(PIN_BUZZER, 0);
}

void io_vibrate(int ms) {
    gpio_set_level(PIN_VIBRATION, 1);
    vTaskDelay(pdMS_TO_TICKS(ms));
    gpio_set_level(PIN_VIBRATION, 0);
}

// Silent confirmation for the child: 3 short vibrations (no sound, so an attacker does not notice).
void io_sos_feedback(void) {
    for (int i = 0; i < 3; i++) { io_vibrate(150); vTaskDelay(pdMS_TO_TICKS(150)); }
}
