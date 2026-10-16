// LIS2DW12 driver (minimal): low-power 12.5 Hz, wake-up interrupt on INT1.
#include "accel.h"
#include "board.h"
#include "driver/i2c.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "accel";

static esp_err_t wr(uint8_t reg, uint8_t val) {
    uint8_t b[2] = {reg, val};
    return i2c_master_write_to_device(I2C_PORT, LIS2DW12_ADDR, b, 2, pdMS_TO_TICKS(50));
}
static esp_err_t rd(uint8_t reg, uint8_t *val) {
    return i2c_master_write_read_device(I2C_PORT, LIS2DW12_ADDR, &reg, 1, val, 1, pdMS_TO_TICKS(50));
}

bool accel_init(void) {
    i2c_config_t cfg = {.mode = I2C_MODE_MASTER, .sda_io_num = PIN_I2C_SDA, .scl_io_num = PIN_I2C_SCL,
                        .sda_pullup_en = false, .scl_pullup_en = false,  // 5.1k on PCB
                        .master.clk_speed = 400000};
    i2c_param_config(I2C_PORT, &cfg);
    i2c_driver_install(I2C_PORT, I2C_MODE_MASTER, 0, 0, 0);

    uint8_t who = 0;
    if (rd(0x0F, &who) != ESP_OK || who != 0x44) {
        ESP_LOGE(TAG, "LIS2DW12 not found (WHO_AM_I=0x%02X)", who);
        return false;
    }
    uint8_t ctrl1 = 0;
    rd(0x20, &ctrl1);
    if (ctrl1 != 0) {        // already configured (woken from deep sleep): keep latched interrupt sources
        ESP_LOGI(TAG, "LIS2DW12 already configured");
        return true;
    }
    wr(0x21, 0x40);          // CTRL2: soft reset (first power-on only)
    vTaskDelay(pdMS_TO_TICKS(10));
    wr(0x21, 0x0C);          // CTRL2: BDU + IF_ADD_INC
    wr(0x20, 0x20);          // CTRL1: ODR 12.5 Hz, low-power mode 1
    wr(0x25, 0x00);          // CTRL6: ±2 g
    wr(0x34, 0x02);          // WAKE_UP_THS: threshold (2 * FS/64)  -> tune in testing
    wr(0x35, 0x00);          // WAKE_UP_DUR
    wr(0x22, 0x18);          // CTRL3: INT active LOW + latched (matches SOS button for ext1 ANY_LOW wake)
    wr(0x23, 0x20);          // CTRL4_INT1: INT1_WU (wake-up)
    wr(0x3F, 0x20);          // CTRL7: interrupts enable
    ESP_LOGI(TAG, "LIS2DW12 ready");
    return true;
}

bool accel_moving(void) {
    uint8_t src = 0;
    rd(0x38, &src);          // WAKE_UP_SRC (reading clears latch)
    return (src & 0x08) != 0;  // WU_IA
}


// ---- Phase 5: fall detection (elderly). Free-fall -> INT2 (GPIO6, wakes the ESP32), then look for the impact.
// NOTE/TODO: thresholds must be tuned with real drops (dummy tests) before release. Not a medical device.
void accel_enable_fall(bool on) {
    if (on) {
        wr(0x36, 0x33);      // FREE_FALL: duration 6 samples, threshold ~312 mg
        wr(0x24, 0x10);      // CTRL5_INT2: INT2_FF (free-fall)
    } else {
        wr(0x24, 0x00);
    }
}

bool accel_fall_event(void) {
    uint8_t src = 0;
    rd(0x3B, &src);          // ALL_INT_SRC (reading clears latched sources)
    return (src & 0x01) != 0;  // FF_IA
}

static int16_t axis(uint8_t lo_reg) {
    uint8_t lo = 0, hi = 0;
    rd(lo_reg, &lo); rd(lo_reg + 1, &hi);
    return (int16_t)((hi << 8) | lo) >> 2;      // 14-bit, ±2 g -> 0.244 mg/LSB
}

bool accel_impact_after(int ms) {
    wr(0x20, 0x50);          // CTRL1: 100 Hz high-performance while checking
    for (int t = 0; t < ms; t += 10) {
        int32_t x = axis(0x28), y = axis(0x2A), z = axis(0x2C);
        int64_t mag2 = (int64_t)x * x + (int64_t)y * y + (int64_t)z * z;
        if (mag2 > (int64_t)8192 * 8192) {      // > ~2 g (8192 LSB at 0.244 mg)
            wr(0x20, 0x20);
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    wr(0x20, 0x20);          // back to low-power 12.5 Hz
    return false;
}
