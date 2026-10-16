// SelfXTrack V1.1 pin map (ESP32-S3-MINI-1-N8) - matches the V1.1 PCB design brief §6.
#pragma once
#include "driver/gpio.h"

#define PIN_BOOT_BTN        GPIO_NUM_0    // SW1 (strap)
#define PIN_CHARGE_DETECT   GPIO_NUM_1    // BQ24073 /CHG  (low = charging)
#define PIN_POWER_DETECT    GPIO_NUM_2    // BQ24073 /PGOOD (low = USB present)
#define PIN_VBAT_ADC        GPIO_NUM_4    // 1M/1M divider -> ADC1
#define PIN_ACC_INT1        GPIO_NUM_5    // LIS2DW12 INT1 (motion wake)
#define PIN_ACC_INT2        GPIO_NUM_6    // LIS2DW12 INT2 (tap / free-fall)
#define PIN_SOS_BTN         GPIO_NUM_7    // SW3 SOS (active low, RTC wake)
#define PIN_I2C_SDA         GPIO_NUM_8
#define PIN_I2C_SCL         GPIO_NUM_9
#define PIN_MODEM_EN        GPIO_NUM_10   // load switch (high = modem powered)
#define PIN_MODEM_PWRKEY    GPIO_NUM_11   // via SS8050 (high = PWRKEY pulled low)
#define PIN_MODEM_RESET     GPIO_NUM_12   // via SS8050
#define PIN_NET_STATUS      GPIO_NUM_13
#define PIN_LED             GPIO_NUM_14
#define PIN_BUZZER          GPIO_NUM_15
#define PIN_VIBRATION       GPIO_NUM_16   // DNP footprint in V1.1 (fit for SOS confirmation)
#define PIN_MODEM_TX        GPIO_NUM_17   // UART1 TX -> modem MAIN_RXD
#define PIN_MODEM_RX        GPIO_NUM_18   // UART1 RX <- modem MAIN_TXD
#define PIN_HALL            GPIO_NUM_21   // DNP Hall sensor (clip detection)

#define MODEM_UART          UART_NUM_1
#define MODEM_BAUD          115200
#define I2C_PORT            I2C_NUM_0
#define LIS2DW12_ADDR       0x19          // SA0 high (check PCB); 0x18 if SA0 low
#define TMP102_ADDR         0x48          // optional (DNP)
