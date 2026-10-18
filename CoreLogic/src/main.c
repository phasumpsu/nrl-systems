#include "../inc/hal.h"
#include "../inc/protocol.h"

#include <arpa/inet.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#define TELEMETRY_PORT 9000

static int listen_for_gui(void)
{
    int listener = socket(AF_INET, SOCK_STREAM, 0);
    if (listener < 0) {
        perror("socket(TCP)");
        return -1;
    }

    int reuse = 1;
    if (setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) < 0) {
        perror("setsockopt(SO_REUSEADDR)");
        close(listener);
        return -1;
    }

    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(TELEMETRY_PORT);
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) < 0 ||
        listen(listener, 1) < 0) {
        perror("bind/listen(TCP)");
        close(listener);
        return -1;
    }
    return listener;
}

static int send_all(int fd, const char *data, size_t length)
{
    while (length > 0) {
        ssize_t sent = send(fd, data, length, MSG_NOSIGNAL);
        if (sent < 0 && errno == EINTR)
            continue;
        if (sent <= 0)
            return -1;
        data += sent;
        length -= (size_t)sent;
    }
    return 0;
}

int main(int argc, char *argv[])
{
    if (argc < 2 || argc > 3 ||
        (strcmp(argv[1], "telemetry-stream-tcp") != 0 &&
         strcmp(argv[1], "telemetry-stream") != 0)) {
        fprintf(stderr, "Usage: %s telemetry-stream[-tcp] [interface]\n", argv[0]);
        return 1;
    }
    bool tcp_mode = strcmp(argv[1], "telemetry-stream-tcp") == 0;
    const char *interface_name = argc == 3 ? argv[2] : "vcan0";
    if (hal_init(interface_name) != 0) {
        fprintf(stderr, "Failed to initialize CAN interface: %s\n", interface_name);
        return 1;
    }

    int listener = -1;
    int client = -1;
    int exit_code = 0;
    if (tcp_mode) {
        listener = listen_for_gui();
        if (listener < 0) {
            exit_code = 1;
            goto cleanup;
        }
    }

    for (;;) {
        if (tcp_mode && client < 0) {
            fprintf(stderr, "Waiting for GUI on TCP port %d\n", TELEMETRY_PORT);
            do {
                client = accept(listener, NULL, NULL);
            } while (client < 0 && errno == EINTR);
            if (client < 0) {
                perror("accept");
                exit_code = 1;
                break;
            }
            struct timeval timeout = {.tv_sec = 1};
            if (setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) < 0) {
                perror("setsockopt(SO_SNDTIMEO)");
                close(client);
                client = -1;
                continue;
            }
            fprintf(stderr, "GUI connected\n");
        }

        struct engine_signal_decoded decoded;
        int result = hal_read_signal(&decoded);
        if (result < 0) {
            fprintf(stderr, "Failed to read CAN frame.\n");
            exit_code = 1;
            break;
        }
        if (result == 1)
            continue;

        char line[512];
        int length = snprintf(line, sizeof(line),"{\"thrust\":%.3f,\"nitrous weight\":%u,\"run tank pressure\":%.3f,\"chamber pressure\":%.3f,\"top temp\":%.3f,\"bot temp\":%.3f,"
        "\"mcu timer\":%.3f,\"sv11_state\":%d,\"sv12_state\":%d,\"sv13_state\":%d,\"ignitor_state\":%d,\"armed_status\":%d,\"routine_sequence\":%d}\n",(double)decoded.engine_thrust, 
            (unsigned)decoded.nitrous_weight,(double)decoded.run_tank_pressure, (double)decoded.cc_pressure,(double)decoded.top_cc_temp, (double)decoded.bot_cc_temp,(double)decoded.timer, 
            decoded.sv11_state, decoded.sv12_state,decoded.sv13_state, decoded.ignitor_state, decoded.armed_status,decoded.routine_sequence);
        if (length < 0 || (size_t)length >= sizeof(line)) {
            fprintf(stderr, "Could not format telemetry line\n");
            exit_code = 1;
            break;
        }

        if (tcp_mode) {
            if (send_all(client, line, (size_t)length) < 0) {
                perror("send(TCP)");
                close(client);
                client = -1;
            }
        } else if (fputs(line, stdout) == EOF || fflush(stdout) == EOF) {
            perror("stdout");
            exit_code = 1;
            break;
        }
    }

cleanup:
    if (client >= 0)
        close(client);
    if (listener >= 0)
        close(listener);
    hal_close();
    return exit_code;
}
