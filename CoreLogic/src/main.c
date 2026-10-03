#include "hal.h"
#include "protocol.h"

#include <stdio.h>
#include <stdint.h>

int main(void)
{
    switch () {
        //Case 1 is for simulations, solely within the software. We will send a fake frame via another terminal, and test whether the actual system is able to receive and send data in a vaccuum.
        case 1:
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
            break;
        //Case 2 is for electronics testing. The ground station sends a frame to the electronics, and it sends a signal back. We both process those signals and ensure proper connection and integration.
        case 2:
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
            break;
        //Case 3 is for the an engine testfire. Data will be continuously flowing from the electronics to the ground station, and we will occassionally send signals to the engine's solenoids/injector. 
        //This is not to be done if an integration AND software check have not been completed, and reported successful. DO NOT DO WTHOUT TESTING THOSE FIRST.
        case 3:
            if (hal_init("can0") != 0) {
                fprintf(stderr, "Failed to initialize CAN interface\n");
                return 1;
            }

            if(hal_read_signal() != 0 ){
                fprintf(stderr, "Failed to read CAN frame.\n");
                hal_close();
                return 1;
            }

            hal_close();
            return 0;
            break;

        //Case 4 is for running the flight engine. As well as the onboard FC, we are going to have a separate engine-only ground station; for recording telemetry and maintaining signal connection. 
        //Note that this is notated for future reference, but will not be implemented until much later. For now, it will act like the default case to prevent misfirings. 
        case 4:
           hal_close();
            return 0;
        //The default case is just to immediately close the terminal. If nothing is happening, then we abort, otherwise an output from any of the other cases might cause confusion. 
        default :
            hal_close();
            return 0;
    }
}