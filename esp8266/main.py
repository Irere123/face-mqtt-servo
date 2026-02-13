# esp8266/main.py
"""
main.py — ESP8266 Face-Tracking Servo Controller (MicroPython)

Subscribes to MQTT topic  vision/<TEAM_ID>/movement  and drives a
servo motor based on face movement commands:

    MOVE_LEFT   → decrement servo angle (pan left)
    MOVE_RIGHT  → increment servo angle (pan right)
    CENTERED    → move to neutral (90°)
    NO_FACE     → hold current position (do nothing)

Servo is driven via PWM on a single GPIO pin (default GPIO2 / D4).

Architecture rule:
    ✅ MQTT only
    ❌ No WebSocket, HTTP, or browser communication
"""

import time
import json
from machine import Pin, PWM
from umqtt.simple import MQTTClient

from config import (
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
    CLIENT_ID,
    SERVO_PIN,
    SERVO_MIN_ANGLE,
    SERVO_MAX_ANGLE,
    SERVO_CENTER,
    SERVO_STEP,
    SERVO_FREQ,
    DUTY_MIN,
    DUTY_MAX,
)


# ─── Servo Control ─────────────────────────────────────────────────

class Servo:
    """Simple servo driver using PWM."""

    def __init__(self, pin, freq=50, duty_min=40, duty_max=115):
        self.pwm = PWM(Pin(pin))
        self.pwm.freq(freq)
        self.duty_min = duty_min
        self.duty_max = duty_max
        self._angle = SERVO_CENTER

    def angle_to_duty(self, angle):
        """Convert angle (0-180) to PWM duty value."""
        angle = max(SERVO_MIN_ANGLE, min(SERVO_MAX_ANGLE, angle))
        # Linear interpolation
        duty = self.duty_min + (self.duty_max - self.duty_min) * angle / 180
        return int(duty)

    def set_angle(self, angle):
        """Move servo to the given angle (0-180)."""
        angle = max(SERVO_MIN_ANGLE, min(SERVO_MAX_ANGLE, angle))
        self._angle = angle
        self.pwm.duty(self.angle_to_duty(angle))

    def get_angle(self):
        return self._angle

    def step_left(self, step=SERVO_STEP):
        """Decrement angle (pan left)."""
        self.set_angle(self._angle - step)

    def step_right(self, step=SERVO_STEP):
        """Increment angle (pan right)."""
        self.set_angle(self._angle + step)

    def center(self):
        """Move to neutral / center position."""
        self.set_angle(SERVO_CENTER)

    def stop(self):
        """Stop PWM signal (release servo)."""
        self.pwm.duty(0)


# ─── MQTT Message Handler ──────────────────────────────────────────

servo = Servo(
    pin=SERVO_PIN,
    freq=SERVO_FREQ,
    duty_min=DUTY_MIN,
    duty_max=DUTY_MAX,
)

# Start at center
servo.center()
print("[Servo] Initialized at {}°".format(servo.get_angle()))


def on_message(topic, msg):
    """
    Handle incoming MQTT messages.

    Expected payload (JSON):
        {"status": "MOVE_LEFT", "confidence": 0.87, "timestamp": 1730000000}
    """
    try:
        payload = json.loads(msg)
        status = payload.get("status", "")
    except (ValueError, KeyError):
        print("[MQTT] Bad message:", msg)
        return

    if status == "MOVE_LEFT":
        servo.step_left()
        print("[Servo] LEFT  -> {}°".format(servo.get_angle()))

    elif status == "MOVE_RIGHT":
        servo.step_right()
        print("[Servo] RIGHT -> {}°".format(servo.get_angle()))

    elif status == "CENTERED":
        servo.center()
        print("[Servo] CENTER -> {}°".format(servo.get_angle()))

    elif status == "NO_FACE":
        # Hold current position — do nothing
        pass

    else:
        print("[MQTT] Unknown status:", status)


# ─── Main Loop ──────────────────────────────────────────────────────

def run():
    """Connect to MQTT and listen for movement commands forever."""

    while True:
        # ── Connect with retry ──
        client = MQTTClient(
            CLIENT_ID,
            MQTT_BROKER,
            port=MQTT_PORT,
        )
        client.set_callback(on_message)

        print("[MQTT] Connecting to", MQTT_BROKER, "...")
        try:
            client.connect()
            client.subscribe(MQTT_TOPIC)
            print("[MQTT] Connected and subscribed to:", MQTT_TOPIC)
            print("[Main] Waiting for movement commands...\n")
        except Exception as e:
            print("[MQTT] Connection failed:", e)
            print("[MQTT] Retrying in 5 seconds...")
            time.sleep(5)
            continue

        # ── Main message loop ──
        try:
            while True:
                client.check_msg()
                time.sleep_ms(50)
        except KeyboardInterrupt:
            print("\n[Main] Stopped by user")
            servo.stop()
            client.disconnect()
            print("[Main] Disconnected. Servo released.")
            return
        except Exception as e:
            print("[MQTT] Error:", e)
            print("[MQTT] Reconnecting in 3 seconds...")
            time.sleep(3)


# Entry point
run()
