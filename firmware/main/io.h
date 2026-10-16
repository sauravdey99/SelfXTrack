#pragma once
#include <stdbool.h>
void io_init(void);
bool io_sos_pressed(void);
void io_led(bool on);
void io_buzz(int ms);
void io_vibrate(int ms);
void io_sos_feedback(void);
