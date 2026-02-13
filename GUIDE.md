# Face-MQTT-Servo — Setup & Deployment Guide

This guide covers:

1. **Environment setup** — clone, venv, dependencies, ArcFace model, camera
2. **Testing modules** — detection, landmarks, alignment, embedding
3. **Enrollment and recognition** — enroll faces, evaluate threshold, run recognition and face locking
4. **Phase 1: Face-tracking servo** — Mosquitto, ESP8266, WebSocket relay, dashboard (fully local)

---

# Part 1 — Environment Setup

## Prerequisites

- **Python**: 3.9+ (verified with 3.11)
- **OS**: macOS, Linux, or Windows
- **Webcam**: USB or built-in camera
- **Disk space**: ~1GB for dependencies + model
- **RAM**: 2GB+ recommended

## Step 1: Clone repository

If starting fresh:

```bash
mkdir -p ~/projects
cd ~/projects
git clone <your-repo-url>
cd face-mqtt-servo
```

Or if you already have the project:

```bash
cd /path/to/face-mqtt-servo
```

## Step 2: Virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\Activate   # Windows PowerShell
python -m pip install --upgrade pip setuptools wheel
```

## Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

If `requirements.txt` is missing:

```bash
pip install opencv-python==4.8.1.78 numpy==1.24.3 onnxruntime==1.16.3 scipy==1.11.2 tqdm==4.66.1 mediapipe==0.10.32 protobuf==4.24.0
```

Verify:

```bash
python -c "import cv2, numpy, onnxruntime, scipy, mediapipe; print('All packages installed')"
```

## Step 4: ArcFace ONNX model

```bash
curl -L -o buffalo_l.zip "https://sourceforge.net/projects/insightface.mirror/files/v0.7/buffalo_l.zip/download"
unzip -o buffalo_l.zip
cp w600k_r50.onnx models/embedder_arcface.onnx
rm -f buffalo_l.zip w600k_r50.onnx 1k3d68.onnx 2d106det.onnx det_10g.onnx genderage.onnx
```

Verify:

```bash
ls -lh models/embedder_arcface.onnx   # ~345MB
```

## Step 5: Camera access

```bash
python -m src.camera
```

- A live camera window should open with FPS. Press **q** to exit.
- **macOS**: System Settings → Privacy & Security → Camera → allow Terminal/VS Code
- **Linux**: `sudo usermod -aG video $USER` then logout/login
- **Windows**: Check Device Manager; try camera index 0 or 1 in config if needed

---

# Part 2 — Test individual modules

Run in order to validate each stage.

| Test | Command | Expected |
|------|---------|----------|
| Face detection | `python -m src.detect` | Green box around face |
| 5-point landmarks | `python -m src.landmarks` | 5 points on face (eyes, nose, mouth) |
| Alignment | `python -m src.align` | 112×112 aligned face (press **s** to save) |
| Embedding | `python -m src.embed` | Prints `embedding dim: 512`, `cos(prev,this): ~0.99` |

If these pass, the core pipeline is working.

---

# Part 3 — Face enrollment

```bash
python -m src.enroll
```

1. Enter a name (e.g. Alice).
2. Position face in camera.
3. **SPACE** = capture one sample; **a** = auto-capture; **s** = save enrollment.
4. Aim for 20–30 samples per person; vary angle and expression.

Repeat for each person. Verify:

```bash
ls -la data/enroll/
cat data/db/face_db.json
```

---

# Part 4 — Threshold evaluation (optional)

```bash
python -m src.evaluate
```

Use the suggested threshold (e.g. 0.34) in recognition; the code uses this for matching.

---

# Part 5 — Live recognition

```bash
python -m src.recognize
```

- Faces labeled with name or "Unknown".
- **+** / **-** adjust threshold; **q** quit.

---

# Part 6 — Face locking (no MQTT/servo)

```bash
python -m src.face_lock
```

1. System lists enrolled faces.
2. Enter the name to track.
3. When found → LOCKED; actions (blink, movement, smile) are logged to `data/face_histories/`.
4. **r** = release lock, **q** = quit.

---

# Part 7 — Phase 1: Face-tracking servo (fully local)

> Everything runs on your PC. No VPS. The servo follows your face: move left → servo left; move right → servo right.

## What happens

```
Your PC (camera + face detection + MQTT broker + dashboard)
    │
    │  MQTT over WiFi
    ▼
ESP8266 + Servo
```

Your PC: (1) detects face and publishes movement via MQTT, (2) runs Mosquitto, (3) runs WebSocket relay + dashboard. The ESP8266 subscribes to MQTT and drives the servo.

## STEP 1 — Install Mosquitto

```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
```

Listen on all interfaces (so ESP on WiFi can connect):

```bash
sudo bash -c 'cat > /etc/mosquitto/conf.d/external.conf << EOF
listener 1883 0.0.0.0
allow_anonymous true
EOF'
sudo systemctl restart mosquitto
sudo systemctl enable mosquitto
```

Verify: `ss -tlnp | grep 1883` should show `0.0.0.0:1883`.

## STEP 2 — PC local IP

```bash
hostname -I | awk '{print $1}'
```

Write this down (e.g. 192.168.1.100); you need it for the ESP8266 config.

## STEP 3 — Python deps for relay/vision

```bash
cd /path/to/face-mqtt-servo
source .venv/bin/activate
pip install paho-mqtt websockets
```

## STEP 4 — Test MQTT

**Terminal 1:**

```bash
mosquitto_sub -h 127.0.0.1 -t "vision/dragonfly/movement" -v
```

**Terminal 2:**

```bash
mosquitto_pub -h 127.0.0.1 -t "vision/dragonfly/movement" -m '{"status":"MOVE_LEFT","confidence":0.87,"timestamp":1730000000}'
```

Terminal 1 should print the message. Then close both.

## STEP 5 — Flash MicroPython on ESP8266

Connect ESP8266 via USB.

```bash
pip install esptool adafruit-ampy
ls /dev/ttyUSB*   # e.g. /dev/ttyUSB0
python -m esptool --port /dev/ttyUSB0 erase_flash
```

Download the latest ESP8266 `.bin` from https://micropython.org/download/esp8266/, then:

```bash
python -m esptool --port /dev/ttyUSB0 --baud 460800 write_flash --flash_size=detect 0 ~/Downloads/ESP8266*.bin
```

## STEP 6 — Edit ESP8266 config

```bash
nano /path/to/face-mqtt-servo/esp8266/config.py
```

Set:

- `WIFI_SSID` / `WIFI_PASSWORD`
- `MQTT_BROKER` = your PC’s IP from Step 2 (for local testing), or your **VPS IP** for submission / live demo

Save and exit.

**Note:** To use your own team ID, set `TEAM_ID` to the same value in `backend/ws_relay.py`, `pc_vision/config.py`, and `esp8266/config.py`. **For submission:** when the broker runs on the VPS, set `MQTT_BROKER` (here) and `MQTT_BROKER_IP` in `pc_vision/config.py` to the VPS IP so PC and ESP8266 both connect to the same broker.

## STEP 7 — MQTT library on ESP8266

```bash
python -m serial.tools.miniterm /dev/ttyUSB0 115200
```

In REPL:

```python
import network
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect('YOUR_WIFI_SSID', 'YOUR_WIFI_PASSWORD')
```

Wait a few seconds, then:

```python
wlan.isconnected()   # should be True
import mip
mip.install('umqtt.simple')
```

Exit: `Ctrl+]`.

## STEP 8 — Upload code to ESP8266

```bash
python -m ampy --port /dev/ttyUSB0 put /path/to/face-mqtt-servo/esp8266/config.py config.py
python -m ampy --port /dev/ttyUSB0 put /path/to/face-mqtt-servo/esp8266/boot.py boot.py
python -m ampy --port /dev/ttyUSB0 put /path/to/face-mqtt-servo/esp8266/main.py main.py
```

## STEP 9 — Wire the servo

| ESP8266 (NodeMCU) | Servo |
|--------------------|-------|
| D4 (GPIO2)         | Signal (orange/yellow) |
| 3V3 or VIN         | Red (power) |
| GND                | Brown (ground) |

If the servo jitters or resets the ESP, power it from a separate 5V supply and share GND.

## STEP 10 — Test ESP8266

Unplug/replug USB or press RESET. In a terminal:

```bash
python -m serial.tools.miniterm /dev/ttyUSB0 115200
```

You should see WiFi and MQTT connect, and “subscribed to: vision/dragonfly/movement”. In another terminal:

```bash
mosquitto_pub -h 127.0.0.1 -t "vision/dragonfly/movement" -m '{"status":"MOVE_LEFT","confidence":0.9,"timestamp":1730000000}'
```

The servo should move. Exit miniterm: `Ctrl+A` then `Ctrl+X`.

## STEP 11 — Run the full stack (3 terminals)

From the project directory, activate venv in each.

**Terminal 1 — WebSocket relay**

```bash
cd /path/to/face-mqtt-servo
source .venv/bin/activate
python backend/ws_relay.py
```

Leave running. You should see “Listening on ws://0.0.0.0:9002”.

**Terminal 2 — Dashboard**

Open `dashboard/index.html` in a browser (e.g. `file:///path/to/face-mqtt-servo/dashboard/index.html`). You should see “Connected”.

**Terminal 3 — Vision**

```bash
cd /path/to/face-mqtt-servo
source .venv/bin/activate
python -m pc_vision.main
```

Enter the name of an enrolled person when prompted. A camera window opens; the servo and dashboard follow your face.

## STEP 12 — Result

- Face left → servo left, dashboard MOVE_LEFT  
- Face right → servo right, dashboard MOVE_RIGHT  
- Centered → CENTERED  
- No face → NO_FACE, servo holds position  

In the camera window: **r** = release lock, **q** = quit.

---

# Directory structure (after setup)

```
face-mqtt-servo/
├── .venv/
├── src/
│   ├── camera.py, detect.py, landmarks.py, align.py, embed.py
│   ├── enroll.py, evaluate.py, recognize.py, haar_5pt.py
│   ├── face_lock.py, action_detector.py, face_history_logger.py
│   └── ...
├── pc_vision/           # MQTT movement publisher
├── server/              # WebSocket relay
├── esp8266/              # MicroPython (config, boot, main)
├── dashboard/            # Browser UI
├── data/
├── models/
│   └── embedder_arcface.onnx
├── requirements.txt
├── README.md
└── GUIDE.md              # This file
```

---

# Troubleshooting

## General / deployment

| Issue | Fix |
|-------|-----|
| `No module named 'mediapipe'` | `pip uninstall -y mediapipe && pip install mediapipe==0.10.32` |
| ONNX / model not found | Ensure `models/embedder_arcface.onnx` exists (~345MB). Re-download from Part 1, Step 4. |
| Camera permission denied | macOS: Privacy → Camera. Linux: `sudo usermod -aG video $USER` and re-login. |
| Empty database for recognize/face_lock | Run `python -m src.enroll` and enroll at least one person. |
| Actions not detected in face_lock | Check `python -m src.landmarks`; adjust thresholds in `action_detector.py`; improve lighting. |

## Phase 1 (servo / MQTT)

| Problem | Fix |
|---------|-----|
| MQTT connection refused | Start Mosquitto: `sudo systemctl start mosquitto` |
| ESP8266 WiFi fails | Check SSID/password in `esp8266/config.py`; re-upload config (Step 6 + 8). |
| ESP can’t reach MQTT | Set `MQTT_BROKER` in `esp8266/config.py` to PC IP (Step 2) or VPS IP for submission. |
| Dashboard “Connecting…” | Start the WebSocket relay in Terminal 1 (`python backend/ws_relay.py`). |
| Camera not found | In `pc_vision/config.py` set `CAMERA_INDEX` to 0 or 1. |
| No enrolled faces | Run `python -m src.enroll` first. |
| `ImportError: umqtt` on ESP | Redo Step 7 (install `umqtt.simple` via mip). |
| Servo jitters | Power servo from external 5V; share GND with ESP. |

---

# Performance tuning (optional)

- **Skip frames** in the vision loop to improve FPS.
- **Lower camera resolution** in `pc_vision/config.py` or capture code (e.g. 640×480).
- **Coarser detection**: increase `scaleFactor` or `minNeighbors` in the Haar cascade.

Typical CPU-only: ~3–5 FPS end-to-end (detection + embedding + action).

---

# Deployment checklist

- [ ] Python 3.9+ and venv created and activated
- [ ] `pip install -r requirements.txt`
- [ ] `python -m src.camera` works
- [ ] At least one person enrolled (`python -m src.enroll`)
- [ ] `python -m src.recognize` and `python -m src.face_lock` work
- [ ] (Phase 1) Mosquitto installed and listening on 0.0.0.0:1883
- [ ] (Phase 1) ESP8266 flashed, config set, code uploaded; relay and dashboard running

---

For project overview and quick links, see [README.md](README.md).
