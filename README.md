# nrl-systems

Data acquisition target: **October 18th** (hard date.)

System: STM32H723ZG (MCU) --CAN FD--> RPi4 (relay + logger) --wireless--> Laptop (ground station/GUI)

---

## to test the software system using vcan0, follow these commands in the terminal (you MUST have linux):
sudo modprobe vcan
sudo ip link add dev vcan- type vcan
sudo ip link set up vcan0 mtu 72
sudo ip link set up vcan0

To verify whether vcan0 is active, do:
ip link show vcan0

Then run this to copy the frame data into the json file for sources.py to receive.
./ground_station telemetry-stream > sample.json

Running the following command will send a frame with the exact length needed. Note that this frame needs to be sent in another terminal:
cansend vcan0 100##00000000000000000000000000000000000000000000000

You can change any zero after the hastags to get differing numbers for the simulated sensor data.

Note that the thermocouples are going to have their own graph, but theyre both for the combustion chamber, to verify the reaction status. 
There is currently only 1 thermocouple able to send data. 

Run this to run the GUI in a raw state:
python -m compileall -q  main.py groundstation
python main.py


Note that for the protocol.dbc, any changest to that has to be mapped to protocol.c and protocol.h using the following:
- cantools generate_c_source --database-name protocol protocol.dbc

---