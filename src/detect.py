# src/detect.py
import argparse

import cv2

try:
    from .camera import open_camera
except ImportError:
    # Run directly: python src/detect.py
    from camera import open_camera


def main(camera_index=None):
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face = cv2.CascadeClassifier(cascade_path)

    if face.empty():
        raise RuntimeError(f"Failed to load cascade: {cascade_path}")

    cap = open_camera(preferred=camera_index)

    print("Haar face detect (minimal). Press 'q' to quit.")

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

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--camera",
        type=int,
        default=None,
        help="Preferred OpenCV camera index, e.g. 1 for an external USB camera",
    )
    args = parser.parse_args()
    main(camera_index=args.camera)
