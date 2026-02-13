# Manual Configuration Guide

Everything you need to do **by hand** before the system works.

---

## 1. VPS — SSH & Mosquitto

```
SSH into VPS:
    ssh user323@157.173.101.159
    Password: 12345678
```

**Install Mosquitto broker:**
```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
```

**Allow external connections** (by default Mosquitto only listens on localhost):
```bash
sudo nano /etc/mosquitto/conf.d/external.conf
```
Paste these two lines:
```
listener 1883 0.0.0.0
allow_anonymous true
```
Then restart:
```bash
sudo systemctl restart mosquitto
sudo systemctl enable mosquitto
```

**Verify** it's listening:
```bash
ss -tlnp | grep 1883
# Should show: *:1883
```

---

## 2. VPS — WebSocket Relay

Upload the `backend/` folder to the VPS (e.g., via `scp`):
```bash
# From your PC:
scp -r backend/ user323@157.173.101.159:~/backend/
```

On the VPS:
```bash
pip3 install paho-mqtt websockets
python3 ~/backend/ws_relay.py
```

> **Tip:** Use `screen` or `tmux` to keep it running after disconnecting:
> ```bash
> screen -S relay
> python3 ~/backend/ws_relay.py
> # Press Ctrl+A, then D to detach
> ```

**Firewall:** Make sure ports **1883** and **9002** are open:
```bash
sudo ufw allow 1883/tcp
sudo ufw allow 9002/tcp
```

---

## 3. PC — Install paho-mqtt

```bash
cd "Face-Locking-with-servo"
source .venv/bin/activate
pip install paho-mqtt
```

**Camera index:** If `CAMERA_INDEX = 2` doesn't work, edit `pc_vision/config.py` and try `0` or `1`.

---

## 4. ESP8266 — Flash MicroPython

### 4a. Download Firmware
- Go to: https://micropython.org/download/esp8266/
- Download the latest `.bin` firmware

### 4b. Flash
```bash
pip install esptool
# Erase existing firmware:
esptool.py --port /dev/ttyUSB0 erase_flash
# Flash MicroPython:
esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash --flash_size=detect 0 esp8266-*.bin
```

> **Port:** On Linux it's usually `/dev/ttyUSB0`. Check with `ls /dev/ttyUSB*`.

### 4c. Install umqtt Library

Connect to the ESP8266 REPL (via Thonny or `picocom /dev/ttyUSB0 -b 115200`):
```python
import upip
upip.install('micropython-umqtt.simple')
```

### 4d. Edit WiFi Credentials

Open `esp8266/config.py` and change:
```python
WIFI_SSID     = "YOUR_ACTUAL_WIFI_NAME"
WIFI_PASSWORD = "YOUR_ACTUAL_WIFI_PASSWORD"
```

### 4e. Upload Files to ESP8266

Using **ampy**:
```bash
pip install adafruit-ampy
ampy --port /dev/ttyUSB0 put esp8266/config.py config.py
ampy --port /dev/ttyUSB0 put esp8266/boot.py boot.py
ampy --port /dev/ttyUSB0 put esp8266/main.py main.py
```

Or use **Thonny IDE** → Open files → Save to MicroPython device.

### 4f. Wiring

```
ESP8266 NodeMCU          Servo Motor (SG90)
───────────────          ──────────────────
D4 (GPIO2)    ──────→    Signal (Orange/Yellow wire)
3V3 or VIN    ──────→    VCC    (Red wire)
GND           ──────→    GND    (Brown wire)
```

> **Important:** If the servo draws too much current from the ESP, use an external 5V power supply for the servo VCC and share GND with the ESP.

---

## 5. Dashboard

No setup needed. Just open `dashboard/index.html` in any browser (Chrome, Firefox, etc.). It will auto-connect to `ws://157.173.101.159:9002`.

---

## Startup Order

1. **VPS:** Start Mosquitto → Start `ws_relay.py`
2. **ESP8266:** Power on (auto-connects WiFi + MQTT)
3. **PC:** Run `python -m pc_vision.main`
4. **Browser:** Open `dashboard/index.html`
