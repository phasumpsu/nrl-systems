#ifndef HAL_H
#define HAL_H

#include "protocol.h"
#include <stdint.h>

//In the hal.h, functions and variables are defined for use in other scripts, mainly for the hal.c to define them. 
//There can be functions in the hal.c that are not defined in the hal.h, but those functions can't be used globally like these can. 
int hal_init(const char *interface_name);
int hal_read_signal(void);
int hal_send_signal(uint8_t ground_sv11, uint8_t run_tank_sv12, uint8_t gauge_sv13, uint8_t fire_injector);
void hal_close(void);

//A decoded version of protocol.dbc is posted here for references in other scripts. 
struct engine_signal_decoded {
    float engine_thrust;
    uint8_t nitrous_weight;
    float run_tank_pressure;
    float cc_pressure;
    float top_cc_temp;
    float bot_cc_temp;
};

#endif