# src/face_lock.py
"""
face_lock.py
Main face locking module — PERFORMANCE-OPTIMIZED.

Key optimizations over the original:
1. Lightweight OpenCV tracker follows the face box between recognition frames.
   Recognition (Haar→FaceMesh→ArcFace ONNX) is expensive (~40ms). The tracker
   just watches pixel motion and costs <1ms.
2. Full recognition runs only every N frames (default 15 ≈ 2× per second at
   30fps). All other frames use the tracker.
3. Small / malformed face detections are rejected before embedding to avoid
   wasting compute on shadows, shirt patterns, etc.

Features:
- Manual identity selection (choose which face to lock)
- Robust face locking with timeout
- Stable tracking across frames
- Action detection while locked
- Persistent action history to file

Run:
python -m src.face_lock
"""

from __future__ import annotations
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np

from .haar_5pt import Haar5ptDetector, align_face_5pt
from .embed import ArcFaceEmbedderONNX
from .action_detector import ActionDetector, Action
from .face_history_logger import FaceHistoryLogger
from .camera_display import CameraDisplay


# =====================================================================
# Face Database & Matcher (from recognize.py, simplified)
# =====================================================================

def load_db_npz(db_path: Path) -> Dict[str, np.ndarray]:
    """Load face database from NPZ file."""
    if not db_path.exists():
        return {}
    data = np.load(str(db_path), allow_pickle=True)
    out: Dict[str, np.ndarray] = {}
    for k in data.files:
        out[k] = np.asarray(data[k], dtype=np.float32).reshape(-1)
    return out


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity (both vectors must be L2-normalized)."""
    a = a.reshape(-1).astype(np.float32)
    b = b.reshape(-1).astype(np.float32)
    return float(np.dot(a, b))


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine distance = 1 - cosine_similarity."""
    return 1.0 - cosine_similarity(a, b)


# =====================================================================
# Face Lock State Machine
# =====================================================================

class FaceLockState:
    """Represents the state of the face lock."""

    SEARCHING = "searching"  # looking for target face
    LOCKED = "locked"  # target face found and locked
    LOST = "lost"  # target face temporarily lost but not released

    def __init__(self):
        self.state = self.SEARCHING
        self.locked_identity: Optional[str] = None
        self.locked_bbox: Optional[Tuple[int, int, int, int]] = None
        self.locked_kps: Optional[np.ndarray] = None
        self.lock_confidence: float = 0.0
        self.frames_since_detection = 0
        self.lock_acquired_time: Optional[float] = None


# =====================================================================
# Main Face Locking System — OPTIMIZED
# =====================================================================

class FaceLockSystem:
    """
    Face locking and action detection system.

    --- Performance Architecture ---
    FAST PATH (most frames):
        OpenCV tracker updates bbox position  →  ~1ms
    SLOW PATH (every Nth frame, or tracker failure):
        Haar detect → FaceMesh 5pt → ArcFace embed → cosine match  →  ~40-60ms

    Workflow:
    1. User selects target identity
    2. System searches for this identity (slow path every frame until found)
    3. When found with high confidence, acquires lock + initializes tracker
    4. While locked, tracker follows face; full recognition runs every N frames
    5. If tracker fails, falls back to full detection immediately
    6. If face disappears for too long, releases lock
    7. User can release lock manually
    """

    def __init__(
        self,
        db_path: Path = Path("data/db/face_db.npz"),
        enroll_dir: Path = Path("data/enroll"),
        model_path: Path = Path("models/embedder_arcface.onnx"),
        distance_threshold: float = 0.54,
        lock_timeout_frames: int = 30,
        min_lock_confidence: float = 0.65,
        recognition_interval: int = 15,
        min_face_size: int = 60,
    ):
        """
        Args:
            db_path: path to face database NPZ
            model_path: path to ArcFace ONNX model
            distance_threshold: cosine distance threshold for recognition
            lock_timeout_frames: frames to wait before releasing lock if face lost
            min_lock_confidence: minimum confidence to acquire lock
            recognition_interval: run full recognition every N frames (default 15)
            min_face_size: minimum face width/height in pixels to consider (noise filter)
        """
        # Load database
        self.db = load_db_npz(db_path)
        self.db_names = sorted(self.db.keys())

        # Initialize components
        self.detector = Haar5ptDetector(min_size=(70, 70), smooth_alpha=0.80, debug=False)
        self.embedder = ArcFaceEmbedderONNX(model_path=model_path, debug=False)
        self.action_detector = ActionDetector()

        # Configuration
        self.distance_threshold = float(distance_threshold)
        self.lock_timeout_frames = int(lock_timeout_frames)
        self.min_lock_confidence = float(min_lock_confidence)
        self.recognition_interval = int(recognition_interval)
        self.min_face_size = int(min_face_size)
        self.min_face_area = self.min_face_size * self.min_face_size

        # State
        self.state = FaceLockState()
        self.history_logger: Optional[FaceHistoryLogger] = None

        # --- Tracking state (NEW) ---
        self._tracker: Optional[cv2.Tracker] = None
        self._tracker_ok: bool = False
        self._frame_count: int = 0
        self._cached_kps: Optional[np.ndarray] = None  # last-known keypoints
        self._cached_confidence: float = 0.0

    # -----------------------------------------------------------------
    # Tracker helpers
    # -----------------------------------------------------------------

    def _create_tracker(self) -> cv2.Tracker:
        """Create a lightweight OpenCV tracker.
        KCF is fast (~1ms) and good enough for face following between
        recognition frames. Falls back to MOSSE if KCF unavailable."""
        try:
            return cv2.TrackerKCF_create()
        except AttributeError:
            pass
        # OpenCV 4.5+ naming
        try:
            return cv2.TrackerKCF.create()
        except AttributeError:
            pass
        # Ultimate fallback: MOSSE (even faster, slightly less accurate)
        try:
            return cv2.legacy.TrackerMOSSE_create()
        except AttributeError:
            return cv2.TrackerMIL.create()

    def _init_tracker(self, frame_bgr: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """Initialize tracker on a confirmed face bounding box."""
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        if w <= 0 or h <= 0:
            self._tracker_ok = False
            return
        self._tracker = self._create_tracker()
        roi = (x1, y1, w, h)
        try:
            self._tracker.init(frame_bgr, roi)
            self._tracker_ok = True
        except Exception:
            self._tracker_ok = False

    def _update_tracker(self, frame_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Update tracker and return new bbox, or None if lost."""
        if self._tracker is None or not self._tracker_ok:
            return None
        try:
            ok, roi = self._tracker.update(frame_bgr)
        except Exception:
            self._tracker_ok = False
            return None
        if not ok:
            self._tracker_ok = False
            return None
        x, y, w, h = [int(v) for v in roi]
        H, W = frame_bgr.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(W, x + w)
        y2 = min(H, y + h)
        if x2 - x1 < 10 or y2 - y1 < 10:
            self._tracker_ok = False
            return None
        return (x1, y1, x2, y2)

    def _is_recognition_frame(self) -> bool:
        """Should we run full (expensive) recognition on this frame?"""
        # Always recognize when searching (need to find target)
        if self.state.state == FaceLockState.SEARCHING:
            return True
        # When locked/lost, only recognize every N frames
        return (self._frame_count % self.recognition_interval) == 0

    # -----------------------------------------------------------------
    # Face filtering (noise rejection)
    # -----------------------------------------------------------------

    def _is_valid_face(self, face) -> bool:
        """Reject faces that are too small or have weird aspect ratios.
        This prevents wasting compute on shadows, patterns, etc."""
        w = face.x2 - face.x1
        h = face.y2 - face.y1
        area = w * h

        # Too small — likely noise
        if area < self.min_face_area:
            return False

        # Weird aspect ratio — faces are roughly square (0.6 to 1.7 ratio)
        if w <= 0 or h <= 0:
            return False
        aspect = w / h
        if aspect < 0.5 or aspect > 2.0:
            return False

        return True

    # -----------------------------------------------------------------
    # Target selection
    # -----------------------------------------------------------------

    def select_target(self, face_name: str) -> bool:
        """
        Select target identity to lock.

        Args:
            face_name: name of enrolled identity

        Returns:
            True if name exists in database, False otherwise
        """
        if face_name.lower() not in [n.lower() for n in self.db_names]:
            return False

        # Match case to database
        for db_name in self.db_names:
            if db_name.lower() == face_name.lower():
                self.state.locked_identity = db_name
                break

        # Initialize history logger
        self.history_logger = FaceHistoryLogger(
            face_name=self.state.locked_identity,
            output_dir=Path("data/face_histories"),
        )
        self.history_logger.log_status(f"Target face selected: {self.state.locked_identity}")

        return True

    # -----------------------------------------------------------------
    # Recognition (expensive)
    # -----------------------------------------------------------------

    def _recognize_face(self, aligned_face: np.ndarray) -> Tuple[Optional[str], float, float]:
        """
        Recognize a single aligned face.

        Returns:
            (identity_name, distance, confidence) or (None, 1.0, 0.0) if unknown
        """
        if not self.db_names:
            return None, 1.0, 0.0

        # Get embedding
        emb_result = self.embedder.embed(aligned_face)
        emb = emb_result.embedding  # Extract numpy array from EmbeddingResult

        # Find best match
        best_name = None
        best_distance = float("inf")
        best_confidence = 0.0

        for db_name in self.db_names:
            db_emb = self.db[db_name]
            dist = cosine_distance(emb, db_emb)

            if dist < best_distance:
                best_distance = dist
                best_name = db_name if dist <= self.distance_threshold else None
                best_confidence = max(0.0, 1.0 - dist)

        return best_name, best_distance, best_confidence

    # -----------------------------------------------------------------
    # Main frame processing — OPTIMIZED
    # -----------------------------------------------------------------

    def process_frame(self, frame_bgr: np.ndarray) -> Dict:
        """
        Process a single frame for face locking and action detection.

        FAST PATH (~1ms): tracker update only — used for most frames
        SLOW PATH (~40ms): full detect+recognize — every Nth frame or on failure

        Args:
            frame_bgr: BGR frame from camera

        Returns:
            Dictionary with state information
        """
        self._frame_count += 1
        now = time.time()

        result = {
            "state": self.state.state,
            "locked_identity": self.state.locked_identity,
            "face_box": self.state.locked_bbox,
            "face_kps": self.state.locked_kps,
            "recognition_distance": None,
            "lock_confidence": self.state.lock_confidence,
            "actions": [],
            "time_locked_seconds": None,
            "all_faces": [],
        }

        # ---------------------------------------------------------------
        # FAST PATH: When locked and not a recognition frame, just track
        # ---------------------------------------------------------------
        if (
            self.state.state in (FaceLockState.LOCKED, FaceLockState.LOST)
            and not self._is_recognition_frame()
            and self._tracker_ok
        ):
            tracked_bbox = self._update_tracker(frame_bgr)

            if tracked_bbox is not None:
                # Tracker succeeded — use tracked position
                self.state.locked_bbox = tracked_bbox
                self.state.state = FaceLockState.LOCKED
                self.state.frames_since_detection = 0

                result["state"] = FaceLockState.LOCKED
                result["face_box"] = tracked_bbox
                result["face_kps"] = self._cached_kps  # use last known kps
                result["lock_confidence"] = self._cached_confidence

                # Still detect actions using cached keypoints (lightweight)
                if self._cached_kps is not None:
                    actions = self.action_detector.detect(self._cached_kps)
                    result["actions"] = actions
                    if self.history_logger:
                        self.history_logger.log_actions(actions)

                # Time locked
                if self.state.lock_acquired_time is not None:
                    result["time_locked_seconds"] = now - self.state.lock_acquired_time

                return result
            else:
                # Tracker failed — fall through to slow path
                self._tracker_ok = False

        # ---------------------------------------------------------------
        # SLOW PATH: Full detection + recognition
        # ---------------------------------------------------------------
        detected_faces = self.detector.detect(frame_bgr, max_faces=3)

        # No faces detected
        if not detected_faces:
            self.state.frames_since_detection += 1

            if self.state.state == FaceLockState.LOCKED:
                if self.state.frames_since_detection > self.lock_timeout_frames:
                    # Timeout, release lock
                    self.state.state = FaceLockState.SEARCHING
                    self.state.locked_bbox = None
                    self.state.locked_kps = None
                    self._tracker_ok = False
                    if self.history_logger:
                        self.history_logger.log_status("Lock LOST (face disappeared)")
                else:
                    # Still in timeout window, hold lock
                    self.state.state = FaceLockState.LOST
                    result["state"] = FaceLockState.LOST

            return result

        # ---------------------------------------------------------------
        # Filter out noise (small / weird faces) BEFORE recognition
        # ---------------------------------------------------------------
        valid_faces = [f for f in detected_faces if self._is_valid_face(f)]
        if not valid_faces:
            # All faces were noise — treat as no detection
            self.state.frames_since_detection += 1
            return result

        # ---------------------------------------------------------------
        # Select which faces to recognize (minimize expensive work)
        # ---------------------------------------------------------------
        self.state.frames_since_detection = 0
        target_face = None
        faces_to_recognize = []

        if self.state.state == FaceLockState.LOCKED and self.state.locked_bbox:
            # LOCKED: Only recognize faces near current lock position
            locked_x1, locked_y1, locked_x2, locked_y2 = self.state.locked_bbox
            locked_cx = (locked_x1 + locked_x2) / 2
            locked_cy = (locked_y1 + locked_y2) / 2
            locked_h = locked_y2 - locked_y1

            threshold_dist = locked_h * 0.75

            for face in valid_faces:
                face_cx = (face.x1 + face.x2) / 2
                face_cy = (face.y1 + face.y2) / 2
                dist = ((face_cx - locked_cx)**2 + (face_cy - locked_cy)**2)**0.5

                if dist < threshold_dist:
                    faces_to_recognize.append(face)

            if not faces_to_recognize:
                largest_face = max(valid_faces, key=lambda f: (f.x2-f.x1)*(f.y2-f.y1))
                faces_to_recognize = [largest_face]
        else:
            # SEARCHING or LOST: Only recognize the largest face
            largest_face = max(valid_faces, key=lambda f: (f.x2-f.x1)*(f.y2-f.y1))
            faces_to_recognize = [largest_face]

        # Recognize selected faces
        for face in faces_to_recognize:
            aligned, _ = align_face_5pt(frame_bgr, face.kps, out_size=(112, 112))
            identity, distance, confidence = self._recognize_face(aligned)

            face_info = {
                "bbox": (face.x1, face.y1, face.x2, face.y2),
                "kps": face.kps.copy(),
                "identity": identity,
                "distance": distance,
                "confidence": confidence,
            }
            result["all_faces"].append(face_info)

            if identity == self.state.locked_identity:
                target_face = (face, identity, distance, confidence)

        # ---------------------------------------------------------------
        # State machine updates
        # ---------------------------------------------------------------
        if target_face:
            face, identity, distance, confidence = target_face
            result["recognition_distance"] = float(distance)
            bbox = (face.x1, face.y1, face.x2, face.y2)

            if self.state.state == FaceLockState.SEARCHING:
                if confidence >= self.min_lock_confidence:
                    # Lock acquired — also initialize tracker
                    self.state.state = FaceLockState.LOCKED
                    self.state.locked_bbox = bbox
                    self.state.locked_kps = face.kps.copy()
                    self.state.lock_confidence = confidence
                    self.state.lock_acquired_time = now
                    self._cached_kps = face.kps.copy()
                    self._cached_confidence = confidence

                    # Initialize tracker for fast path
                    self._init_tracker(frame_bgr, bbox)

                    result["state"] = FaceLockState.LOCKED
                    result["face_box"] = bbox
                    result["face_kps"] = self.state.locked_kps
                    result["lock_confidence"] = confidence

                    if self.history_logger:
                        self.history_logger.log_status(
                            f"Lock ACQUIRED for {self.state.locked_identity} (confidence={confidence:.3f})"
                        )

            elif self.state.state == FaceLockState.LOCKED:
                # Update tracked position + refresh tracker
                self.state.locked_bbox = bbox
                self.state.locked_kps = face.kps.copy()
                self.state.lock_confidence = confidence
                self._cached_kps = face.kps.copy()
                self._cached_confidence = confidence

                # Re-initialize tracker with fresh detection
                self._init_tracker(frame_bgr, bbox)

                result["state"] = FaceLockState.LOCKED
                result["face_box"] = bbox
                result["face_kps"] = self.state.locked_kps
                result["lock_confidence"] = confidence

                # Detect actions while locked
                actions = self.action_detector.detect(face.kps)
                result["actions"] = actions
                if self.history_logger:
                    self.history_logger.log_actions(actions)

            elif self.state.state == FaceLockState.LOST:
                if confidence >= self.min_lock_confidence:
                    # Lock re-acquired
                    self.state.state = FaceLockState.LOCKED
                    self.state.locked_bbox = bbox
                    self.state.locked_kps = face.kps.copy()
                    self.state.lock_confidence = confidence
                    self._cached_kps = face.kps.copy()
                    self._cached_confidence = confidence

                    # Re-initialize tracker
                    self._init_tracker(frame_bgr, bbox)

                    result["state"] = FaceLockState.LOCKED
                    result["face_box"] = bbox
                    result["face_kps"] = self.state.locked_kps

                    if self.history_logger:
                        self.history_logger.log_status(
                            f"Lock RE-ACQUIRED for {self.state.locked_identity}"
                        )
        else:
            # Target face NOT found
            if self.state.state == FaceLockState.LOCKED:
                self.state.frames_since_detection += 1
                if self.state.frames_since_detection > self.lock_timeout_frames:
                    self.state.state = FaceLockState.SEARCHING
                    self.state.locked_bbox = None
                    self.state.locked_kps = None
                    self._tracker_ok = False
                    if self.history_logger:
                        self.history_logger.log_status("Lock LOST (target not found)")
                else:
                    self.state.state = FaceLockState.LOST
                    result["state"] = FaceLockState.LOST

        # Time locked
        if self.state.lock_acquired_time is not None and self.state.state in (
            FaceLockState.LOCKED,
            FaceLockState.LOST,
        ):
            result["time_locked_seconds"] = now - self.state.lock_acquired_time

        return result

    def release_lock(self) -> None:
        """Manually release the lock."""
        if self.state.state in (FaceLockState.LOCKED, FaceLockState.LOST):
            self.state.state = FaceLockState.SEARCHING
            self.state.locked_bbox = None
            self.state.locked_kps = None
            self.state.lock_acquired_time = None
            self._tracker_ok = False
            self._tracker = None
            if self.history_logger:
                self.history_logger.log_status("Lock RELEASED by user")

    def finalize_session(self) -> str:
        """
        Finalize the locking session and save history.

        Returns:
            path to history file
        """
        if self.history_logger:
            return self.history_logger.finalize()
        return ""


# =====================================================================
# UI & Demo
# =====================================================================

def _put_text(img, text: str, xy=(10, 30), scale=0.8, thickness=2):
    """Draw text with white color and black outline."""
    cv2.putText(img, text, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2)
    cv2.putText(img, text, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thickness)


def main():
    """Interactive face locking demo."""
    # Load system WITHOUT opening camera yet
    system = FaceLockSystem(
        enroll_dir=Path("data/enroll"),
        distance_threshold=0.54,
        recognition_interval=15,  # full recognition every 15 frames
        min_face_size=60,  # ignore faces smaller than 60x60
    )
    
    # Get available faces
    if not system.db_names:
        print("No enrolled faces found. Run enrollment first.")
        return

    print("\n" + "=" * 80)
    print("FACE LOCKING SYSTEM (OPTIMIZED)")
    print("=" * 80)
    print(f"\nAvailable faces: {', '.join(system.db_names)}\n")

    # User selects target BEFORE opening camera
    while True:
        target = input("Select face to lock (or 'q' to quit): ").strip()
        if target.lower() == "q":
            return
        if system.select_target(target):
            print(f"✓ Target selected: {target}")
            break
        print(f"✗ Face '{target}' not found. Try again.")

    # NOW open camera after selection
    cap = cv2.videoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Camera not available")
    
    # Create large display manager
    display = CameraDisplay(mode=CameraDisplay.LARGE)
    display.create_window("Face Locking", resizable=True)

    print("\nStarting face locking...")
    print("Controls:")
    print("  r  : release lock")
    print("  q  : quit")
    print("=" * 80 + "\n")

    t0 = time.time()
    frames = 0
    fps = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            # Process frame (fast path for most frames!)
            result = system.process_frame(frame)

            # Visualize
            vis = frame.copy()
            H, W = vis.shape[:2]

            # Draw ALL detected faces with recognition labels
            for face_info in result["all_faces"]:
                x1, y1, x2, y2 = face_info["bbox"]
                identity = face_info["identity"] if face_info["identity"] else "Unknown"
                confidence = face_info["confidence"]
                
                # Color: green for target locked, yellow for recognized, red for unknown
                if identity == result["locked_identity"] and result["state"] == "locked":
                    color = (0, 255, 0)  # Green for locked target
                elif identity != "Unknown":
                    color = (0, 255, 255)  # Yellow for recognized
                else:
                    color = (0, 0, 255)  # Red for unknown
                
                # Draw bounding box
                cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
                
                # Draw label with confidence
                label = f"{identity} ({confidence:.2f})"
                cv2.putText(
                    vis,
                    label,
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                )

            # Draw state indicator
            state_text = result["state"].upper()
            if result["state"] == "locked":
                state_color = (0, 255, 0)
            elif result["state"] == "lost":
                state_color = (0, 165, 255)
            else:
                state_color = (0, 0, 255)

            cv2.rectangle(vis, (5, 5), (W - 5, 50), (0, 0, 0), -1)
            cv2.putText(
                vis,
                f"Lock: {state_text} | Target: {result['locked_identity']}",
                (15, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                state_color,
                2,
            )

            # Draw detected face if locked
            if result["state"] in ("locked", "lost") and result["face_box"]:
                x1, y1, x2, y2 = result["face_box"]
                color = state_color
                thickness = 3 if result["state"] == "locked" else 2
                cv2.rectangle(vis, (x1, y1), (x2, y2), color, thickness)

                # Draw landmarks
                if result["face_kps"] is not None:
                    for (x, y) in result["face_kps"].astype(int):
                        cv2.circle(vis, (int(x), int(y)), 3, color, -1)

                # Draw info
                info_y = y1 - 10 if y1 > 40 else y2 + 20
                conf_text = f"Conf: {result['lock_confidence']:.2f}"
                if result["time_locked_seconds"] is not None:
                    time_text = f" | Time: {result['time_locked_seconds']:.1f}s"
                else:
                    time_text = ""

                cv2.putText(
                    vis,
                    conf_text + time_text,
                    (x1, info_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                )

                # Show actions detected
                if result["actions"]:
                    action_text = " | ".join([a.action_type for a in result["actions"]])
                    cv2.putText(
                        vis,
                        f"Actions: {action_text}",
                        (x1, info_y + 25),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 255),
                        2,
                    )

            # FPS
            frames += 1
            dt = time.time() - t0
            if dt >= 1.0:
                fps = frames / dt
                frames = 0
                t0 = time.time()

            cv2.putText(
                vis,
                f"FPS: {fps:.1f}",
                (W - 150, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            cv2.imshow("Face Locking", vis)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("r"):
                system.release_lock()
                print("✗ Lock released by user")

    finally:
        cap.release()
        cv2.destroyAllWindows()

        # Finalize
        history_file = system.finalize_session()
        print(f"\n✓ Session ended")
        print(f"✓ History saved to: {history_file}")
        if system.history_logger:
            print(system.history_logger.get_summary())


if __name__ == "__main__":
    main()
