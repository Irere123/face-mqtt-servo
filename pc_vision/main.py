# pc_vision/main.py
"""
PC Vision Node — Entry Point

Opens the camera, runs the face-locking system, derives movement
state (MOVE_LEFT / MOVE_RIGHT / CENTERED / NO_FACE), and publishes
changes over MQTT to the VPS broker.

Architecture:
    Camera → FaceLockSystem → MovementDetector → MQTTPublisher
                                                     ↓
                                              MQTT Broker (VPS)

Usage:
    cd Face-Locking-with-servo
    python -m pc_vision.main

Controls:
    r : release lock
    q : quit
"""

from __future__ import annotations
import sys
import time
from pathlib import Path

import cv2

# Add project root so we can import from src.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.face_lock import FaceLockSystem
from src.camera_display import CameraDisplay
from pc_vision.config import CAMERA_INDEX, MQTT_TOPIC_MOVEMENT
from pc_vision.movement_detector import MovementDetector
from pc_vision.mqtt_publisher import MQTTPublisher


def main():
    # ── 1. Initialize face-lock system ──────────────────────────────
    system = FaceLockSystem(
        enroll_dir=Path("data/enroll"),
        distance_threshold=0.54,
        recognition_interval=15,
        min_face_size=60,
    )

    if not system.db_names:
        print("No enrolled faces found. Run enrollment first:")
        print("  python -m src.enroll")
        return

    print("\n" + "=" * 70)
    print("PC VISION NODE — PHASE 1 (MQTT Publisher)")
    print("=" * 70)
    print(f"Available faces: {', '.join(system.db_names)}")
    print(f"MQTT topic:      {MQTT_TOPIC_MOVEMENT}\n")

    # ── 2. Select target identity ───────────────────────────────────
    while True:
        target = input("Select face to lock (or 'q' to quit): ").strip()
        if target.lower() == "q":
            return
        if system.select_target(target):
            print(f"✓ Target selected: {target}")
            break
        print(f"✗ Face '{target}' not found. Try again.")

    # ── 3. Connect MQTT ─────────────────────────────────────────────
    mqtt_pub = MQTTPublisher()
    try:
        mqtt_pub.connect()
    except ConnectionError as e:
        print(f"\n✗ {e}")
        print("  Make sure Mosquitto is running on the VPS.")
        return

    # ── 4. Initialize movement detector ─────────────────────────────
    movement = MovementDetector()

    # ── 5. Open camera ──────────────────────────────────────────────
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"✗ Camera index {CAMERA_INDEX} not available")
        mqtt_pub.disconnect()
        return

    display = CameraDisplay(mode=CameraDisplay.LARGE)
    display.create_window("PC Vision Node", resizable=True)

    print("\nStreaming started. Controls: r=release lock, q=quit")
    print("=" * 70 + "\n")

    t0 = time.time()
    frames = 0
    fps = 0.0
    last_status_printed = ""

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            H, W = frame.shape[:2]

            # ── Process frame (fast-path optimized) ─────────────────
            result = system.process_frame(frame)

            # ── Derive movement and publish ─────────────────────────
            payload = movement.compute(result, frame_width=W)
            if payload is not None:
                mqtt_pub.publish_movement(payload)
                # Print status changes to terminal
                if payload["status"] != last_status_printed:
                    print(f"  → {payload['status']}  (conf={payload['confidence']:.2f})")
                    last_status_printed = payload["status"]

            # ── Visualize ───────────────────────────────────────────
            vis = frame.copy()

            # State bar
            state = result["state"].upper()
            if result["state"] == "locked":
                sc = (0, 255, 0)
            elif result["state"] == "lost":
                sc = (0, 165, 255)
            else:
                sc = (0, 0, 255)

            cv2.rectangle(vis, (5, 5), (W - 5, 50), (0, 0, 0), -1)
            cv2.putText(vis, f"Lock: {state} | Target: {result['locked_identity']}",
                        (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, sc, 2)

            # Movement status overlay
            mv = payload["status"] if payload else (last_status_printed or "---")
            cv2.putText(vis, f"MQTT: {mv}", (15, H - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            # Face box
            if result["face_box"]:
                x1, y1, x2, y2 = result["face_box"]
                cv2.rectangle(vis, (x1, y1), (x2, y2), sc, 3)
                if result["face_kps"] is not None:
                    for (px, py) in result["face_kps"].astype(int):
                        cv2.circle(vis, (int(px), int(py)), 3, sc, -1)

            # Center dead-zone guide lines
            cxl = int(W / 2 - W * movement.dead_zone_ratio)
            cxr = int(W / 2 + W * movement.dead_zone_ratio)
            cv2.line(vis, (cxl, 0), (cxl, H), (200, 200, 200), 1)
            cv2.line(vis, (cxr, 0), (cxr, H), (200, 200, 200), 1)

            # FPS
            frames += 1
            dt = time.time() - t0
            if dt >= 1.0:
                fps = frames / dt
                frames = 0
                t0 = time.time()
            cv2.putText(vis, f"FPS: {fps:.1f}", (W - 150, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow("PC Vision Node", vis)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("r"):
                system.release_lock()
                print("  ✗ Lock released by user")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        mqtt_pub.disconnect()
        history = system.finalize_session()
        print(f"\n✓ Session ended")
        if history:
            print(f"✓ History: {history}")


if __name__ == "__main__":
    main()
