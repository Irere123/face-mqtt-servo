# src/camera.py
"""
Shared camera helpers.

open_camera() tries several indices and verifies frames can actually be
read (on macOS a capture can report isOpened() yet deliver no frames).
Run this module directly for a quick camera test:
python -m src.camera
"""
import argparse
from typing import Optional, Sequence

import cv2

DEFAULT_INDICES = (0, 1, 2, 3)


def open_camera(
    preferred: Optional[int] = None,
    indices: Sequence[int] = DEFAULT_INDICES,
    warmup_frames: int = 3,
) -> cv2.VideoCapture:
    """
    Open the first working camera and return its capture.
    A `preferred` index is tried first, then the rest of `indices`.
    Raises RuntimeError if no camera delivers frames.
    """
    order = list(indices)
    if preferred is not None:
        order = [int(preferred)] + [i for i in order if i != int(preferred)]
    for idx in order:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ok = False
            for _ in range(max(1, warmup_frames)):
                ok, _ = cap.read()
                if ok:
                    break
            if ok:
                print(f"[camera] using camera index {idx}")
                return cap
        cap.release()
    raise RuntimeError(f"No working camera found. Tried indices: {order}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index",
        "--camera",
        dest="index",
        type=int,
        default=None,
        help="Preferred camera index to try first, e.g. 1 for an external USB camera",
    )
    args = parser.parse_args()

    cap = open_camera(preferred=args.index)

    print("Camera test. Press 'q' to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Failed to read frame.")
            break

        cv2.imshow("Camera Test", frame)

        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
