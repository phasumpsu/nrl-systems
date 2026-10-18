# NRL Ground Station 2.0

---

## Quick start

```bash
pip install -r requirements.txt
python -m compileall -q main.py groundstation
python main.py

## Layout

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


