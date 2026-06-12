"""
vision_node.py
Simulated Vision Node for Distributed Vision-Control System.
Tracks face and publishes movement commands via MQTT.
Topic: vision/team313/movement
"""

import time
import argparse
import csv
import cv2
import json
import numpy as np
try:
    import paho.mqtt.client as mqtt
except Exception as e:
    mqtt = None
    _MQTT_IMPORT_ERROR = e
from pathlib import Path
import sys
import base64

# Add src to path if needed
sys.path.append(str(Path(__file__).parent.parent))

# Import Face Locking modules
from src.camera import open_camera
from src.haar_5pt import Haar5ptDetector
from src.recognize import ArcFaceEmbedderONNX, FaceDBMatcher, load_db_npz
from src.face_locking import FaceLockSystem, LockState

# Configuration
DEFAULT_BROKER = "localhost"  # override with --broker <ip> on exam day
PORT = 1883
TEAM_ID = "dragonfly"
TOPIC_MOVEMENT = f"vision/{TEAM_ID}/movement"
TOPIC_HEARTBEAT = f"vision/{TEAM_ID}/heartbeat"
# Snapshots carry a base64 JPEG (tens of KB). They go on their own topic so the
# movement topic stays tiny: the ESP8266 PubSubClient buffer is only 256 bytes
# and silently drops any packet bigger than that.
TOPIC_SNAPSHOT = f"vision/{TEAM_ID}/snapshot"



class VisionNode:
    def __init__(self, broker, port, target_name, dist_thresh=0.60, camera_index=None):
        if mqtt is None:
            raise RuntimeError(
                f"paho-mqtt import failed: {_MQTT_IMPORT_ERROR}\n"
                "Install dependencies with: pip install -r requirements.txt"
            )
        self.camera_index = camera_index

        # MQTT Setup (paho-mqtt 2.x callback API)
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{TEAM_ID}_vision_node",
        )
        self.client.on_connect = self.on_connect
        self.client.connect(broker, port, 60)
        self.client.loop_start()
        
        # Face Recognition & Locking Setup
        print("Initializing Face Recognition...")
        self.det = Haar5ptDetector(min_size=(70, 70))
        self.embedder = ArcFaceEmbedderONNX(input_size=(112, 112))
        
        # Load Database
        db_path = Path(__file__).parent.parent / "data/db/face_db.npz"
        if not db_path.exists():
            print(f"ERROR: Face DB not found at {db_path}. Run enroll.py first!")
            sys.exit(1)
            
        db = load_db_npz(db_path)
        if target_name not in db:
            print(f"WARNING: Target '{target_name}' not in database. Available: {list(db.keys())}")
        
        self.matcher = FaceDBMatcher(db, dist_thresh=dist_thresh)
        self.system = FaceLockSystem(target_name, self.matcher, self.det)

        self.running = True
        self.last_heartbeat = 0
        self.last_publish_time = 0
        self.mqtt_topic = TOPIC_MOVEMENT
        self.snapshot_sent = False  # Track if we've sent the face snapshot

        # Evidence log (Activity 5): timestamp, speaker, confidence, command
        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = log_dir / f"commands_{time.strftime('%Y%m%d%H%M%S')}.csv"
        with open(self.log_file, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["timestamp", "iso_time", "speaker", "confidence", "command", "locked"]
            )
        print(f"[log] Evidence log: {self.log_file}")

    def on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connected to MQTT Broker with result code {reason_code}")
        self.publish_heartbeat()

    def log_command(self, ts, speaker, confidence, command, locked):
        with open(self.log_file, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                f"{ts:.3f}",
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
                speaker,
                f"{float(confidence):.4f}",
                command,
                int(locked),
            ])

    def publish_movement(self, status, confidence=0.0, target=None, locked=False, face_image=None):
        now = time.time()
        payload = {
            "status": status,
            "confidence": round(float(confidence), 4),
            "target": target,
            "locked": locked,
            "timestamp": now
        }

        self.client.publish(self.mqtt_topic, json.dumps(payload))

        # The (large) face snapshot goes to its own topic for the dashboard only
        if face_image is not None:
            _, buffer = cv2.imencode('.jpg', face_image, [cv2.IMWRITE_JPEG_QUALITY, 70])
            snap = dict(payload)
            snap["face_image"] = base64.b64encode(buffer).decode('utf-8')
            self.client.publish(TOPIC_SNAPSHOT, json.dumps(snap))

        self.log_command(now, target, confidence, status, locked)
        print(f"Published: {status} (conf={confidence:.2f}, image: {'yes' if face_image is not None else 'no'})")

    def publish_heartbeat(self):
        payload = {
            "node": "pc_vision",
            "status": "ONLINE",
            "timestamp": time.time()
        }
        self.client.publish(TOPIC_HEARTBEAT, json.dumps(payload))

    def run(self):
        # Try multiple indices so it works across different machines
        cap = open_camera(preferred=self.camera_index)
        
        print(f"Vision Node Started. Tracking target: {self.system.target_name}")
        print(f"Publishing to {TOPIC_MOVEMENT}")
        
        while self.running:
            ret, frame = cap.read()
            if not ret: break
            
            # Flip for mirror effect
            frame = cv2.flip(frame, 1)
            H, W = frame.shape[:2]
            
            # Process Frame using FaceLockSystem
            # process_frame returns (vis_frame, target_face_obj, lock_state)
            vis, target_face, lock_state = self.system.process_frame(frame, self.embedder)
            
            status = "NO_FACE"
            face_crop = None

            if lock_state == LockState.SEARCHING:
                # Explicitly searching for the target -> tell ESP to sweep
                status = "NO_FACE"
                if self.snapshot_sent:
                    self.snapshot_sent = False
                    print("🔓 Target lost - snapshot flag reset")
            elif lock_state == LockState.LOCKED:
                if target_face:
                    # Target is found and currently locked
                    f = target_face

                    # Extract face crop for dashboard (only if not sent yet)
                    if not self.snapshot_sent:
                        x1, y1, x2, y2 = int(f.x1), int(f.y1), int(f.x2), int(f.y2)
                        # Add padding
                        pad = 20
                        x1 = max(0, x1 - pad)
                        y1 = max(0, y1 - pad)
                        x2 = min(W, x2 + pad)
                        y2 = min(H, y2 + pad)
                        face_crop = frame[y1:y2, x1:x2]
                        self.snapshot_sent = True  # Mark as sent
                        print("📸 Face snapshot captured and will be sent")

                    # Calculate Center
                    cx = (f.x1 + f.x2) / 2.0
                    cx_norm = cx / W

                    # Movement Logic
                    # Deadband: 0.4 to 0.6 is CENTERED
                    if cx_norm < 0.4:
                        status = "MOVE_LEFT"
                    elif cx_norm > 0.6:
                        status = "MOVE_RIGHT"
                    else:
                        status = "CENTERED"
                else:
                    # Temporarily lost target but still within LOCKED hysteresis.
                    # Hold position: repeating the last MOVE_* at 10 Hz would pan
                    # the camera away from a briefly occluded speaker.
                    status = "CENTERED"

            # --- RATE LIMITING (10Hz) ---
            current_time = time.time()
            if current_time - self.last_publish_time >= 0.1:
                is_locked = (status != "NO_FACE")
                self.publish_movement(
                    status,
                    confidence=self.system.last_similarity,
                    target=self.system.target_name,
                    locked=is_locked,
                    face_image=face_crop,
                )
                self.last_publish_time = current_time
            
            # Heartbeat every 5s
            if time.time() - self.last_heartbeat > 5:
                self.publish_heartbeat()
                self.last_heartbeat = time.time()
            
            cv2.imshow("Vision Node (Locked)", vis)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
        self.client.loop_stop()
        self.client.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", type=str, default=DEFAULT_BROKER, help="MQTT Broker Address")
    parser.add_argument("--name", type=str, default="irere", help="Target name to lock onto")
    parser.add_argument(
        "--thresh", type=float, default=0.60,
        help="Cosine DISTANCE threshold (lower = stricter). Tune with: python -m src.evaluate",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=None,
        help="Preferred OpenCV camera index, e.g. 1 for an external USB camera",
    )
    args = parser.parse_args()

    node = VisionNode(
        args.broker,
        PORT,
        args.name,
        dist_thresh=args.thresh,
        camera_index=args.camera,
    )
    node.run()
