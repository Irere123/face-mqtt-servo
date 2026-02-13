# pc_vision/mqtt_publisher.py
"""
MQTT publisher for the PC Vision Node.

Uses paho-mqtt to connect to the Mosquitto broker on the VPS and
publish movement messages to  vision/<team_id>/movement .

Architecture rule enforced:
    ✅ MQTT only
    ❌ No WebSocket, HTTP, or direct ESP communication from PC.
"""

from __future__ import annotations
import json
import time
from typing import Dict

import paho.mqtt.client as mqtt

from .config import (
    MQTT_BROKER_IP,
    MQTT_BROKER_PORT,
    MQTT_KEEPALIVE,
    MQTT_TOPIC_MOVEMENT,
    TEAM_ID,
)


class MQTTPublisher:
    """Manages MQTT connection and publishes movement messages."""

    def __init__(self):
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"pc_vision_{TEAM_ID}",
            protocol=mqtt.MQTTv311,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._connected = False

    # ── Callbacks ───────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0 or rc == mqtt.CONNACK_ACCEPTED:
            self._connected = True
            print(f"[MQTT] Connected to {MQTT_BROKER_IP}:{MQTT_BROKER_PORT}")
        else:
            print(f"[MQTT] Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, flags=None, rc=None, properties=None):
        self._connected = False
        if rc is not None and rc != 0:
            print(f"[MQTT] Unexpected disconnect (rc={rc}), will auto-reconnect")

    # ── Public API ──────────────────────────────────────────────────

    def connect(self) -> None:
        """Connect to the MQTT broker (blocking until connected)."""
        print(f"[MQTT] Connecting to {MQTT_BROKER_IP}:{MQTT_BROKER_PORT} ...")
        self._client.connect(
            MQTT_BROKER_IP,
            MQTT_BROKER_PORT,
            keepalive=MQTT_KEEPALIVE,
        )
        self._client.loop_start()

        # Wait for connection (up to 10 seconds)
        t0 = time.time()
        while not self._connected and (time.time() - t0) < 10:
            time.sleep(0.1)

        if not self._connected:
            raise ConnectionError(
                f"Failed to connect to MQTT broker at {MQTT_BROKER_IP}:{MQTT_BROKER_PORT}"
            )

    def publish_movement(self, payload: Dict) -> None:
        """
        Publish a movement message.

        Args:
            payload: dict with keys "status", "confidence", "timestamp"
        """
        msg = json.dumps(payload)
        self._client.publish(
            MQTT_TOPIC_MOVEMENT,
            msg,
            qos=1,
        )

    def disconnect(self) -> None:
        """Cleanly disconnect from the broker."""
        self._client.loop_stop()
        self._client.disconnect()
        print("[MQTT] Disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected
