# src/camera.py
import cv2
from .camera_display import CameraDisplay


def main():
    cap = cv2.videoCapture(0)

    if not cap.isOpened():
        raise RuntimeError("Camera not opened. Try changing index (0/1/2).")

    # Create large display
    display = CameraDisplay(mode=CameraDisplay.LARGE)
    display.create_window("Camera Test", resizable=True)

    print("Camera test. Press 'q' to quit.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Failed to read frame.")
                break

            cv2.imshow("Camera Test", frame)

            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                break

    finally:
        cap.release()
        display.close_all()


if __name__ == "__main__":
    main()
