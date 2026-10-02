# nrl-systems

Data acquisition target: **October 18th** (hard date.)

System: STM32H723ZG (MCU) --CAN FD--> RPi4 (relay + logger) --wireless--> Laptop (ground station/GUI)

---

## GUI
- [ ] fix the GUI so that it uses actual data
- [ ] change the output graphs so that it shows the correct data
- [ ] each of the sensors (Load cells, transducers, thermocouples) are going to have 2 lines in their graphs; one for the run tank, the other for the combustion chamber. 


## Shared Resources
- [ ] .dbc file (+ checksum/CRC)
- [ ] csv schema: column format for loggers (seq_num, timestamp, sensor fields, CRC/status).
- [ ] timestamp/sequence strategy: mcu hardware timer in every CAN frame; used to reconcile logs after the fact.

---

## MCU (STM32H723ZG)
- [ ] peripheral config (FDCAN init, filters, bit timing)
- [ ] main.c
- [ ] hal.h/hal.c
- [ ] sensor sampling code (interrupt/DMA driven)
- [ ] CAN receiver for incoming commands (switch/solenoid valve states) from ground
- [ ] csv logger to onboard SD card (SDMMC + FatFS)
- [ ] switch + solenoid valve control code (state machine, driven by received commands)
- [ ] watchdog / fault handling

---

## RPI4 (relay + logger)
- [ ] socketcan / can fd interface setup (SPI-CAN controller + can0 config)
- [ ] CSV logger, independent process
- [ ] relay process: forwards live telemetry to laptop (different messages)
- [ ] pass commands from laptop to MCU (valve/switch control)
- [ ] systemd services for logger + relay to run independently (important!!)

---

## Laptop (ground station)
- [ ] live checksum/sequence checker on incoming telemetry stream (flags OK / CRC_FAIL / GAP).
- [ ] dashboard/GUI already made by my vehement goat, caio nishiyama, just needs integration.
- [ ] command interface: send switch/valve using physical buttons (important!!) (3 solenoid, 1 ignitor).
- [ ] post-mission bulk transfer script — pull csv from MCU + RPI (rsync/scp).
- [ ] file-integrity check after transfer before finalization (checksum compare, e.g. sha256).

---

## Notes
- things need to be done in parts, many things require others to start.

