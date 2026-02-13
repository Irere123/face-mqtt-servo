# pc_vision/config.py
"""
Configuration for the PC Vision MQTT publisher.
Edit these values to match your deployment environment.
"""

# ─── MQTT Broker (localhost — everything runs on this PC) ───────────
MQTT_BROKER_IP = "127.0.0.1"
MQTT_BROKER_PORT = 1883
MQTT_KEEPALIVE = 60  # seconds

# ─── Team Isolation ─────────────────────────────────────────────────
TEAM_ID = "team01"
MQTT_TOPIC_MOVEMENT = f"vision/{TEAM_ID}/movement"
MQTT_TOPIC_HEARTBEAT = f"vision/{TEAM_ID}/heartbeat"

# ─── Movement Detection ────────────────────────────────────────────
# Face position thresholds relative to frame center.
# If the face center is within ±DEAD_ZONE_RATIO of frame center → CENTERED.
# Outside that → MOVE_LEFT or MOVE_RIGHT.
DEAD_ZONE_RATIO = 0.12  # 12% of frame width on each side of center

# ─── Anti-Flooding ──────────────────────────────────────────────────
# Only publish when state CHANGES, but also re-publish the current
# state at most once every MIN_PUBLISH_INTERVAL seconds (heartbeat).
MIN_PUBLISH_INTERVAL = 0.5  # seconds between forced re-publishes

# ─── Camera ─────────────────────────────────────────────────────────
CAMERA_INDEX = 0  # OpenCV VideoCapture index (change if needed)
