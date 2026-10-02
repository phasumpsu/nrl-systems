#include "hal.h"
#include "protocol.h"

#include <stdio.h>
#include <stdint.h>

int main(void)
{
    if (hal_init("vcan0") != 0) {
        fprintf(stderr, "Failed to initialize CAN interface\n");
        return 1;
    }

    printf("CAN interface initialized\n");
    printf("Waiting for a CAN frame...\n");

    if(hal_read_signal() != 0 ){
        fprintf(stderr, "Failed to read CAN frame.\n");
        hal_close();
        return 1;
    }

    /*if(hal_send_signal(uint8_t sv11, uint8_t sv12, uint8_t sv13, uint8_t fire_injector) != 0){
        fprintf(stderr, "Failed to send CAN frame.\n");
        hal_close();
        return 1;
    }*/

    hal_close();
    return 0;
}