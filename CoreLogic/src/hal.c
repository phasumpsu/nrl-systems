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
// -1 means no socket is currently open. A non-negative number means there is a valid file descriptor.

int hal_init(const char *interface_name)
{
    struct sockaddr_can address;
    struct ifreq interface_request;
    
    can_socket = socket(PF_CAN, SOCK_RAW, CAN_RAW);/*
    PF_CAN = Use the Linux CAN protocol family (it's supported natively).
    SOCK_RAW = Receive the raw CAN frames.
    CAN_RAW = Use the raw CAN protocol.*/

    if (can_socket < 0) {
        perror("socket");
        return -1;
    }

    int enable_fd = 1;
    setsockopt(can_socket, SOL_CAN_RAW, CAN_RAW_FD_FRAMES, &enable_fd, sizeof(enable_fd));

    memset(&interface_request, 0, sizeof(interface_request));
    strncpy(interface_request.ifr_name, interface_name, IFNAMSIZ - 1);

    if (ioctl(can_socket, SIOCGIFINDEX, &interface_request) < 0) {
        perror("ioctl");
        close(can_socket);
        can_socket = -1;
        return -1;
    }

    memset(&address, 0, sizeof(address));
    address.can_family = AF_CAN;
    address.can_ifindex = interface_request.ifr_ifindex;

    if (bind(can_socket, (struct sockaddr *)&address, sizeof(address)) < 0) {
        perror("bind");
        close(can_socket);
        can_socket = -1;
        return -1;
    }

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

    /*All of the data, that's copied from protocol.dbc.*/
    uint16_t engine_thrust_raw = (uint16_t)data[0] | (uint16_t)data[1] << 8;
    uint8_t nitrous_weight_raw = data[2];
    uint16_t run_tank_pressure_raw = (uint16_t)data[3] | (uint16_t)data[4] << 8;
    uint16_t cc_pressure_raw = (uint16_t)data[5] | (uint16_t)data[6] << 8;
    uint16_t top_cc_temp_raw = (uint16_t)data [7] | (uint16_t)data[8] << 8;
    uint16_t bot_cc_temp_raw = (uint16_t)data[9] | (uint16_t)data[10] << 8;
    
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

    if (can_socket < 0) {
        fprintf(stderr, "CAN socket is not initialized\n");
        return -1;
    }

    bytes_read = read(can_socket, &frame, sizeof(frame));

    if (bytes_read < 0) {
        perror("read");
        return -1;
    }

    if (bytes_read != CANFD_MTU && bytes_read != CAN_MTU) {
        fprintf(stderr, "Unexpected frame size: %zd bytes\n", bytes_read);
        return -1;
    }

    if(frame.can_id != 0x100){
        return -1;
    }

    if(frame.len < 11){
        fprintf(stderr, "Engine frame is too short\n");
        return -1;
    }

    if (decode_signal(frame.data, &decoded) != 0)
        return -1;

    // create some type of conditional testing input for this first hand. Might be a seperatte functiont o implement in
    // the main.c. up for confirmation later. 
    test_frame(frame);

    return 0;
}





int hal_send_signal(uint8_t ground_sv11, uint8_t run_tank_sv12, uint8_t gauge_sv13, uint8_t fire_injector){
    struct canfd_frame frame = {0};

    if (can_socket < 0) {
        fprintf(stderr, "CAN socket is not initialized\n");
        return -1;
    }

    frame.can_id = 0x200;
    frame.len = 16;

    frame.data[0] = (ground_sv11 & 0x0Fu) | ((run_tank_sv12 & 0x0Fu) << 4);
    frame.data[1] = (gauge_sv13 & 0x0Fu) | ((fire_injector & 0x0Fu) << 4);

    ssize_t byte_written = write(can_socket, &frame, CANFD_MTU);

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
