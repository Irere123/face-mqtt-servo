# src/detect.py
import cv2
from .camera_display import CameraDisplay


def main():
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face = cv2.CascadeClassifier(cascade_path)

    if face.empty():
        raise RuntimeError(f"Failed to load cascade: {cascade_path}")

    cap = cv2.videoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Camera not opened. Try camera index 0/1/2.")

    # Create large display
    display = CameraDisplay(mode=CameraDisplay.LARGE)
    display.create_window("Face Detection", resizable=True)

    print("Haar face detect (minimal). Press 'q' to quit.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # minimal but practical defaults
            faces = face.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(60, 60),
            )

            for x, y, w, h in faces:
                cv2.rectangle(
                    frame,
                    (x, y),
                    (x + w, y + h),
                    (0, 255, 0),
                    2,
                )

            cv2.imshow("Face Detection", frame)

            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                break

    finally:
        cap.release()
        display.close_all()


if __name__ == "__main__":
    main()
