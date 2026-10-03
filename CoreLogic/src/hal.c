#define _DEFAULT_SOURCE

#include "hal.h"

#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <net/if.h>
#include <linux/can.h>
#include <linux/can/raw.h>

static int can_socket = -1;
// -1 means no socket is currently open. A non-negative number means there is an open socket file descriptor.

int hal_init(const char *interface_name)
{
    struct sockaddr_can address;
    struct ifreq interface_request;
    
    can_socket = socket(PF_CAN, SOCK_RAW, CAN_RAW);/*
    -PF_CAN = Use the Linux CAN protocol family (it's supported natively).
    -SOCK_RAW = Provides raw access to the CAN frames.
    -CAN_RAW = Use the raw CAN protocol.*/

    if (can_socket < 0) {
        perror("socket");
        return -1;
    }

    //CAN FD, specifically, is not on by default, and it needs to be enabled to allow CAN FD frames to be received and sent. 
    int enable_fd = 1;
    if(setsockopt(can_socket, SOL_CAN_RAW, CAN_RAW_FD_FRAMES, &enable_fd, sizeof(enable_fd)) < 0){
        perror("setsockopt(CAN_RAW_FD_FRAMES)");
        close(can_socket);
        can_socket = -1;
        return -1;
    }

    //This temporarily defines interface_request, by setting each byte of the request to 0.
    memset(&interface_request, 0, sizeof(interface_request));

    //This copies the requested interface name ('can0') into the ifreq structure, 
        //for each 'byte - 1', to reduce the chance of a null terminator).
    strncpy(interface_request.ifr_name, interface_name, IFNAMSIZ - 1);

    //ioctl stands for 'input/output control'. 
    //This asks the kernel for the interface index associated with the interface name (in this case, 'can0'),
        //returning -1 if the operation failed. If successful, the index is saved into interface_request.ifr_ifindex.
    if (ioctl(can_socket, SIOCGIFINDEX, &interface_request) < 0) {
        perror("ioctl");
        close(can_socket);
        can_socket = -1;
        return -1;
    }

    //Now, we save that index as the address for the CAN socket.

    //These initialize the CAN socket address structure. 
    //The interface index found above is used to identify which CAN interface the socket 
        //should be assiociated with when bind() is called.
    memset(&address, 0, sizeof(address));
    address.can_family = AF_CAN;
    address.can_ifindex = interface_request.ifr_ifindex;

    //So, if all of that worked, it would be able to bind the socket to that address so that we are able to send and receive a CAN frame. 
    if (bind(can_socket, (struct sockaddr *)&address, sizeof(address)) < 0) {
        perror("bind");
        close(can_socket);
        can_socket = -1;
        return -1;
    }

    // bind() associates the socket with the selected CAN interface, allowing it to send/receive CAN frames through that interface.

    return 0;
}

int test_frame(struct canfd_frame frame){
    printf("Received CAN frame\n");
    printf("CAN ID: 0x%X\n", frame.can_id & CAN_EFF_MASK);
    printf("Length: %u\n", frame.len);
    printf("Data:");

    for (unsigned int i = 0; i < frame.len; i++) {
        printf(" %02X", frame.data[i]);
    }

    printf("\n");

    return 0;
}

static int decode_signal(const uint8_t data[24], struct engine_signal_decoded *output){
    if (data == NULL || output == NULL)
        return -1;

    /*Raw signal data that's decoded according to the byte layout from protocol.dbc.*/
    uint16_t engine_thrust_raw = (uint16_t)data[0] | (uint16_t)data[1] << 8;
    uint8_t nitrous_weight_raw = data[2];
    uint16_t run_tank_pressure_raw = (uint16_t)data[3] | (uint16_t)data[4] << 8;
    uint16_t cc_pressure_raw = (uint16_t)data[5] | (uint16_t)data[6] << 8;
    uint16_t top_cc_temp_raw = (uint16_t)data [7] | (uint16_t)data[8] << 8;
    uint16_t bot_cc_temp_raw = (uint16_t)data[9] | (uint16_t)data[10] << 8;
    
    /* Takes the raw inputs from the engine and scales them by however much protocol.dbc defines*/
    output->engine_thrust = engine_thrust_raw * 0.1f;
    output->nitrous_weight = nitrous_weight_raw;
    output->run_tank_pressure = run_tank_pressure_raw * 0.1f;
    output->cc_pressure = cc_pressure_raw * 0.1f;
    output->top_cc_temp = top_cc_temp_raw * 0.1f;
    output->bot_cc_temp = bot_cc_temp_raw * 0.1f;
    
    return 0;
}

int hal_read_signal(void)
{
    struct canfd_frame frame;
    ssize_t bytes_read;
    struct engine_signal_decoded decoded;

    //Check if the can socket is initialized.
    if (can_socket < 0) {
        fprintf(stderr, "CAN socket is not initialized\n");
        return -1;
    }

    bytes_read = read(can_socket, &frame, sizeof(frame));

    //Check if we're able to read the frame.
    if (bytes_read < 0) {
        perror("read");
        return -1;
    }

    //Verifies if the frame is a classic CAN frame or CANFD frame. 
    if (bytes_read != CANFD_MTU && bytes_read != CAN_MTU) {
        fprintf(stderr, "Unexpected frame size: %zd bytes\n", bytes_read);
        return -1;
    }

    //Ensure that the frame ID is 0x100,
        //defined as the engine signal message from protocol.dbc. 
    if(frame.can_id != 0x100){
        return -1;
    }

    //This checks whether the frame we have contains enough payload bytes for all the information we want to decode. 
    if(frame.len < 11){
        fprintf(stderr, "Engine frame is too short\n");
        return -1;
    }

    //Check if we are able to decode the frame.
    if (decode_signal(frame.data, &decoded) != 0)
        return -1;

    //This function is separate just because the current function was getting messy. 
    test_frame(frame);

    return 0;
}

int hal_send_signal(uint8_t ground_sv11, uint8_t run_tank_sv12, uint8_t gauge_sv13, uint8_t fire_injector){
    struct canfd_frame frame = {0};

    if (can_socket < 0) {
        fprintf(stderr, "CAN socket is not initialized\n");
        return -1;
    }

    // The frame parameters are that its ID is 0x200 and its length is 16 bytes. 
    frame.can_id = 0x200;
    frame.len = 16;

    //Packs two 4-bit acutator values into 1 byte. 
    //ground_sv11 occupies bits 0-3, while run_tank_sv12 occupies bits 4-7.
        //gauge_sv13 occupies bits 8-11, while fire_injector occupies bits 12-15.
    frame.data[0] = (ground_sv11 & 0x0Fu) | ((run_tank_sv12 & 0x0Fu) << 4);
    frame.data[1] = (gauge_sv13 & 0x0Fu) | ((fire_injector & 0x0Fu) << 4);

    ssize_t byte_written = write(can_socket, &frame, CANFD_MTU);

    //Check that the format is correct before exiting the function. 
    if (byte_written != CANFD_MTU){
        perror("write");
        return -1;
    }

    return 0;
}

void hal_close(void)
{
    if (can_socket >= 0) {
        close(can_socket);
        can_socket = -1;
    }
}
