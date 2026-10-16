#include "power.h"
#include "board.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"

static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_cali;
#define VBAT_CH ADC_CHANNEL_3   // GPIO4 = ADC1_CH3 on ESP32-S3

void power_init(void) {
    adc_oneshot_unit_init_cfg_t u = {.unit_id = ADC_UNIT_1};
    adc_oneshot_new_unit(&u, &s_adc);
    adc_oneshot_chan_cfg_t c = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    adc_oneshot_config_channel(s_adc, VBAT_CH, &c);
    adc_cali_curve_fitting_config_t cc = {.unit_id = ADC_UNIT_1, .atten = ADC_ATTEN_DB_12,
                                          .bitwidth = ADC_BITWIDTH_DEFAULT};
    adc_cali_create_scheme_curve_fitting(&cc, &s_cali);

    gpio_config_t in = {.pin_bit_mask = (1ULL << PIN_CHARGE_DETECT) | (1ULL << PIN_POWER_DETECT),
                        .mode = GPIO_MODE_INPUT};  // external 10k pull-ups on PCB
    gpio_config(&in);
}

int power_battery_mv(void) {
    int sum = 0, raw, mv;
    for (int i = 0; i < 8; i++) { adc_oneshot_read(s_adc, VBAT_CH, &raw); sum += raw; }
    adc_cali_raw_to_voltage(s_cali, sum / 8, &mv);
    return mv * 2;  // 1M / 1M divider
}

// Simple Li-Po discharge curve (rest voltage). Refine with real battery data.
int power_battery_percent(void) {
    static const int mv_tab[] = {3300, 3500, 3600, 3700, 3750, 3800, 3850, 3900, 4000, 4100, 4200};
    int mv = power_battery_mv();
    if (mv <= mv_tab[0]) return 0;
    for (int i = 1; i < 11; i++)
        if (mv < mv_tab[i]) return (i - 1) * 10 + (mv - mv_tab[i - 1]) * 10 / (mv_tab[i] - mv_tab[i - 1]);
    return 100;
}

bool power_usb_present(void) { return gpio_get_level(PIN_POWER_DETECT) == 0; }
bool power_charging(void) { return gpio_get_level(PIN_CHARGE_DETECT) == 0; }
