from machine import Pin, PWM
from umqtt.simple import MQTTClient
import time
import ujson

# Configuration
# Set this to the IP of the machine running the MQTT broker
MQTT_BROKER = "10.12.75.96"
CLIENT_ID = "esp8266_dragonfly"
TOPIC_SUB = b"vision/dragonfly/movement"
TOPIC_PUB = b"vision/dragonfly/heartbeat"

# Servo Configuration
# SG90 Servo: 50Hz PWM. Duty cycle usually 40-115 for 0-180 degrees.
SERVO_PIN = 14  # D5 on NodeMCU
servo = PWM(Pin(SERVO_PIN), freq=50)

# Positions (Duty values for 0, 90, 180 degrees approx)
# 10-bit resolution (0-1023)
MIN_DUTY = 40
MAX_DUTY = 115
CENTER_DUTY = 77

TRACK_STEP = 3          # duty units per MOVE_LEFT / MOVE_RIGHT command
SWEEP_STEP = 1          # duty units per sweep tick while searching
SWEEP_INTERVAL_MS = 60  # sweep tick period
FACE_TIMEOUT_MS = 2000  # silence on movement topic -> back to search mode

current_duty = CENTER_DUTY
searching = True        # start in search mode until the target is found
sweep_dir = SWEEP_STEP
last_face_ms = 0


def set_servo(duty):
    global current_duty
    # Clamp
    if duty < MIN_DUTY:
        duty = MIN_DUTY
    if duty > MAX_DUTY:
        duty = MAX_DUTY
    servo.duty(duty)
    current_duty = duty


def sub_cb(topic, msg):
    global searching, last_face_ms
    try:
        data = ujson.loads(msg)
        status = data.get("status", "")

        # Direction matches vision_servo.ino: LEFT decreases the angle.
        # If your mounting tracks the wrong way, swap the +/- signs below.
        if status == "MOVE_LEFT":
            searching = False
            last_face_ms = time.ticks_ms()
            set_servo(current_duty - TRACK_STEP)
        elif status == "MOVE_RIGHT":
            searching = False
            last_face_ms = time.ticks_ms()
            set_servo(current_duty + TRACK_STEP)
        elif status == "CENTERED":
            # Target centered: hold position
            searching = False
            last_face_ms = time.ticks_ms()
        elif status == "NO_FACE":
            # Speaker lost / occluded: enter controlled search sweep
            searching = True

    except Exception as e:
        print("Error parsing JSON:", e)


def main():
    global searching, sweep_dir
    print("Starting MQTT Client...")

    # Initialize Servo to Center
    set_servo(CENTER_DUTY)

    try:
        client = MQTTClient(CLIENT_ID, MQTT_BROKER)
        client.set_callback(sub_cb)
        client.connect()
        print("Connected to MQTT Broker:", MQTT_BROKER)
        client.subscribe(TOPIC_SUB)
        print("Subscribed to:", TOPIC_SUB)

        last_heartbeat = 0
        last_sweep = time.ticks_ms()

        while True:
            # Check for messages
            client.check_msg()
            now = time.ticks_ms()

            # Watchdog: no command for FACE_TIMEOUT_MS -> resume searching
            if not searching and time.ticks_diff(now, last_face_ms) > FACE_TIMEOUT_MS:
                print("Face lost! Starting search sweep...")
                searching = True

            # Non-blocking search sweep between MIN and MAX
            if searching and time.ticks_diff(now, last_sweep) > SWEEP_INTERVAL_MS:
                last_sweep = now
                nxt = current_duty + sweep_dir
                if nxt >= MAX_DUTY:
                    nxt = MAX_DUTY
                    sweep_dir = -SWEEP_STEP
                elif nxt <= MIN_DUTY:
                    nxt = MIN_DUTY
                    sweep_dir = SWEEP_STEP
                set_servo(nxt)

            # Heartbeat every 10s
            if time.time() - last_heartbeat > 10:
                payload = ujson.dumps(
                    {"node": "esp8266", "status": "ONLINE", "uptime": time.time()}
                )
                client.publish(TOPIC_PUB, payload)
                last_heartbeat = time.time()

            time.sleep_ms(20)

    except Exception as e:
        print("Error:", e)
        print("Rebooting in 5 seconds...")
        time.sleep(5)
        import machine
        machine.reset()


if __name__ == "__main__":
    main()
