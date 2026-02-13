# Setup & Testing Commands — Complete Reference

All commands for every component, in execution order.

---

## 1. VPS Setup (157.173.101.159)

```bash
# SSH in
ssh user323@157.173.101.159
# Password: 12345678

# Install Mosquitto MQTT broker
sudo apt update && sudo apt install -y mosquitto mosquitto-clients

# Allow external connections
echo -e "listener 1883 0.0.0.0\nallow_anonymous true" | sudo tee /etc/mosquitto/conf.d/external.conf
sudo systemctl restart mosquitto
sudo systemctl enable mosquitto

# Verify Mosquitto is listening
ss -tlnp | grep 1883

# Open firewall ports
sudo ufw allow 1883/tcp
sudo ufw allow 9002/tcp

# Install Python deps for WebSocket relay
pip3 install paho-mqtt websockets

# Upload backend (run from your PC, not VPS)
# scp -r backend/ user323@157.173.101.159:~/backend/

# Start WebSocket relay (on VPS)
python3 ~/backend/ws_relay.py

# (Optional) Run in background with screen:
# screen -S relay
# python3 ~/backend/ws_relay.py
# Ctrl+A, D to detach
# screen -r relay   to reattach
```

---

## 2. MQTT Testing

```bash
# Subscribe (run on VPS or PC — shows incoming messages):
mosquitto_sub -h 157.173.101.159 -t "vision/team01/movement" -v

# Simulate MOVE_LEFT:
mosquitto_pub -h 157.173.101.159 -t "vision/team01/movement" \
  -m '{"status":"MOVE_LEFT","confidence":0.87,"timestamp":1730000000}'

# Simulate MOVE_RIGHT:
mosquitto_pub -h 157.173.101.159 -t "vision/team01/movement" \
  -m '{"status":"MOVE_RIGHT","confidence":0.92,"timestamp":1730000001}'

# Simulate CENTERED:
mosquitto_pub -h 157.173.101.159 -t "vision/team01/movement" \
  -m '{"status":"CENTERED","confidence":0.95,"timestamp":1730000002}'

# Simulate NO_FACE:
mosquitto_pub -h 157.173.101.159 -t "vision/team01/movement" \
  -m '{"status":"NO_FACE","confidence":0.0,"timestamp":1730000003}'

# Verify topic isolation (this should NOT receive any messages):
mosquitto_sub -h 157.173.101.159 -t "vision/otherteam/movement" -v
```

---

## 3. PC Vision Node

```bash
cd "Face-Locking-with-servo"
source .venv/bin/activate

# Install MQTT client (one-time)
pip install paho-mqtt

# Enroll faces first (if not already done)
python -m src.enroll

# Run the vision node
python -m pc_vision.main

# Controls while running:
#   r : release lock
#   q : quit
```

---

## 4. ESP8266 Flashing

```bash
# Install tools (one-time, on PC)
pip install esptool adafruit-ampy

# Erase flash
esptool.py --port /dev/ttyUSB0 erase_flash

# Flash MicroPython
esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash --flash_size=detect 0 esp8266-*.bin

# Install umqtt (connect to REPL first)
# >>> import upip
# >>> upip.install('micropython-umqtt.simple')

# Upload files
ampy --port /dev/ttyUSB0 put esp8266/config.py config.py
ampy --port /dev/ttyUSB0 put esp8266/boot.py boot.py
ampy --port /dev/ttyUSB0 put esp8266/main.py main.py

# Monitor serial output
picocom /dev/ttyUSB0 -b 115200
# or: screen /dev/ttyUSB0 115200
```

---

## 5. WebSocket Testing

```bash
# Quick test from terminal (requires wscat):
npm install -g wscat
wscat -c ws://157.173.101.159:9002

# Or just open dashboard/index.html in a browser.
# Then send an MQTT message (Section 2) and verify it appears.
```

---

## 6. End-to-End Verification Checklist

```
[ ] Mosquitto running on VPS (port 1883)
[ ] ws_relay.py running on VPS (port 9002)
[ ] mosquitto_sub shows messages from PC
[ ] Dashboard connects and shows updates
[ ] ESP8266 connects WiFi (check serial output)
[ ] ESP8266 receives MQTT and servo moves
[ ] Simulated messages (mosquitto_pub) work end-to-end
[ ] PC vision node publishes on face movement
```

---

## 7. Stopping Everything

```bash
# PC: press 'q' in the vision window

# VPS: Ctrl+C on ws_relay.py
# VPS: sudo systemctl stop mosquitto  (if you want to stop broker)

# ESP8266: just unplug power
```
