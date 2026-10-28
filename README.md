# nrl-systems

Data acquisition target: **November... 8th?** (soft date.)

System: STM32H723ZG (MCU) --CAN FD--> RPi4 (relay + logger) --wireless--> Laptop (ground station/GUI)

---

## NEEDED BEFORE RUNNING
If you've never ran VS Code or have done anything with GitHub/Repositories, PLEASE do these steps first:

**Install Git**: https://git-scm.com/install/windows (you can access the Linux/Mac versions using this link)

Then run in VS Code's terminal:

git clone https://github.com/phasumpsu/nrl-systems.git

Now, you must open a virtual environment (venv) within this repo. Run:

python 

(^this is to download python to ensure you can use python commands. Then:)

python -m venv venv

(^this creates a new folder called venv that'll help you compile everything)

venv\Scripts\activate.bat   [<< For Windows in Command Prompt]
venv\Scripts\Activate.ps1   [<< For Windows in Powershell]
source venv/bin/activate    [<< For Linux/Mac]

**If you did it right, your terminal will prefix with ".venv"!**
*Common Mistakes:* Case Sensitive commands, wrong slashes used, misspelled words. AKA, just copy + paste.

Then, please run:

pip install -r requirements.txt

(^This downloads all of the dependencies that the repository uses to function, just all in one download)
**NOTE**:*Not all of the downloads can download. If you're using Windows/Mac, you will not be able to run "can-utils", but that isn't necessary for running the GUI (thankfully).

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

Run this to run the GUI in a raw state:
python -m compileall -q  FC_UI/main.py FC_UI/groundstation
python FC_UI/main.py


Note that for the protocol.dbc, any changes to that has to be mapped to protocol.c and protocol.h using the following:
- cantools generate_c_source --database-name protocol protocol.dbc
- The thermocouples are going to have their own graph, but theyre both for the combustion chamber, to verify the reaction status. 
There is currently only 1 thermocouple able to send data. 

```
+-------------------------------------------------------------------+
| toolbar:  NRL | source | connect | link state                      |
+------------+--------------------------------+---------------------+
| ATTITUDE   |  FLIGHT PHASE banner + track   |  GPS TRAJECTORY     |
| 3D + r/p/y |--------------------------------|  (Leaflet)          |
|------------|  ALTITUDE                      |---------------------|
| PYRO       |  ACCELERATION                  |  VEHICLE STATUS     |
| CHANNELS   |  VERTICAL VELOCITY             |  (stat tiles)       |
+------------+--------------------------------+---------------------+
| EVENT LOG                                                         |
+-------------------------------------------------------------------+
```

---


on the groundstation, when connected to "systems RPi" run:

ping 10.42.0.1 [or whatever the current IP address is of the Pi.]