# src/test_face_locking.py
"""
test_face_locking.py
Comprehensive test suite for Face Locking system.

Run this to verify all components work correctly.

Usage:
    python -m src.test_face_locking
"""

import sys
import time
from pathlib import Path
import numpy as np

# Try imports
def test_imports():
    """Test all required imports."""
    print("\n" + "="*80)
    print("TEST 1: Importing Dependencies")
    print("="*80)
    
    try:
        import cv2
        print("✓ OpenCV (cv2)")
    except ImportError as e:
        print(f"✗ OpenCV: {e}")
        return False
    
    try:
        import numpy
        print("✓ NumPy")
    except ImportError as e:
        print(f"✗ NumPy: {e}")
        return False
    
    try:
        import onnxruntime
        print("✓ ONNX Runtime")
    except ImportError as e:
        print(f"✗ ONNX Runtime: {e}")
        return False
    
    try:
        import mediapipe
        print("✓ MediaPipe")
    except ImportError as e:
        print(f"✗ MediaPipe: {e}")
        return False
    
    try:
        import scipy
        print("✓ SciPy")
    except ImportError as e:
        print(f"✗ SciPy: {e}")
        return False
    
    print("\n✓ All dependencies imported successfully")
    return True


def test_modules():
    """Test internal modules."""
    print("\n" + "="*80)
    print("TEST 2: Importing Project Modules")
    print("="*80)
    
    try:
        from src.action_detector import ActionDetector
        print("✓ action_detector.ActionDetector")
    except ImportError as e:
        print(f"✗ action_detector: {e}")
        return False
    
    try:
        from src.face_history_logger import FaceHistoryLogger
        print("✓ face_history_logger.FaceHistoryLogger")
    except ImportError as e:
        print(f"✗ face_history_logger: {e}")
        return False
    
    try:
        from src.face_lock import FaceLockSystem
        print("✓ face_lock.FaceLockSystem")
    except ImportError as e:
        print(f"✗ face_lock: {e}")
        return False
    
    try:
        from src.haar_5pt import Haar5ptDetector
        print("✓ haar_5pt.Haar5ptDetector")
    except ImportError as e:
        print(f"✗ haar_5pt: {e}")
        return False
    
    try:
        from src.embed import ArcFaceEmbedderONNX
        print("✓ embed.ArcFaceEmbedderONNX")
    except ImportError as e:
        print(f"✗ embed: {e}")
        return False
    
    print("\n✓ All project modules imported successfully")
    return True


def test_model_file():
    """Test if model file exists."""
    print("\n" + "="*80)
    print("TEST 3: Model File Verification")
    print("="*80)
    
    model_path = Path("models/embedder_arcface.onnx")
    
    if not model_path.exists():
        print(f"✗ Model file not found: {model_path}")
        print("  Please download ArcFace model:")
        print("  curl -L -o buffalo_l.zip 'https://sourceforge.net/projects/insightface.mirror/files/v0.7/buffalo_l.zip/download'")
        print("  unzip -o buffalo_l.zip")
        print("  cp w600k_r50.onnx models/embedder_arcface.onnx")
        return False
    
    size_mb = model_path.stat().st_size / (1024 * 1024)
    print(f"✓ Model file found: {model_path}")
    print(f"  Size: {size_mb:.1f} MB")
    
    # Expected size ~345 MB
    if size_mb < 300:
        print(f"  ⚠ Warning: Model size seems small ({size_mb:.1f}MB), expected ~345MB")
        return False
    
    print("\n✓ Model file verified")
    return True


def test_directories():
    """Test required directories."""
    print("\n" + "="*80)
    print("TEST 4: Directory Structure")
    print("="*80)
    
    required_dirs = [
        Path("src"),
        Path("data"),
        Path("data/db"),
        Path("data/enroll"),
        Path("models"),
    ]
    
    for dir_path in required_dirs:
        if dir_path.exists():
            print(f"✓ {dir_path}/")
        else:
            print(f"✗ {dir_path}/ - MISSING")
            return False
    
    # Auto-create face_histories
    history_dir = Path("data/face_histories")
    if not history_dir.exists():
        history_dir.mkdir(parents=True, exist_ok=True)
        print(f"✓ {history_dir}/ (created)")
    else:
        print(f"✓ {history_dir}/")
    
    print("\n✓ Directory structure verified")
    return True


def test_action_detector():
    """Test ActionDetector functionality."""
    print("\n" + "="*80)
    print("TEST 5: ActionDetector Unit Test")
    print("="*80)
    
    from src.action_detector import ActionDetector
    
    detector = ActionDetector()
    print("✓ ActionDetector initialized")
    
    # Create fake landmarks
    fake_kps = np.array([
        [100.0, 100.0],  # left_eye
        [150.0, 100.0],  # right_eye
        [125.0, 150.0],  # nose_tip
        [110.0, 180.0],  # left_mouth
        [140.0, 180.0],  # right_mouth
    ], dtype=np.float32)
    
    # Test detection
    actions = detector.detect(fake_kps)
    print(f"✓ Detected {len(actions)} actions from fake landmarks")
    
    # Test multiple frames for blink detection
    for i in range(5):
        actions = detector.detect(fake_kps)
    
    print("✓ ActionDetector can process frame sequences")
    return True


def test_history_logger():
    """Test FaceHistoryLogger functionality."""
    print("\n" + "="*80)
    print("TEST 6: FaceHistoryLogger Unit Test")
    print("="*80)
    
    from src.face_history_logger import FaceHistoryLogger
    from src.action_detector import Action
    
    # Create logger
    logger = FaceHistoryLogger(
        face_name="TestPerson",
        output_dir=Path("data/face_histories"),
    )
    print(f"✓ FaceHistoryLogger initialized")
    print(f"  File: {logger.filepath}")
    
    # Create fake action
    action = Action(
        action_type="blink",
        timestamp=time.time(),
        confidence=0.85,
        value=0.45,
        description="Test blink detection",
    )
    
    # Log action
    logger.log_action(action)
    print(f"✓ Logged 1 action")
    
    # Log status
    logger.log_status("Test status message")
    print(f"✓ Logged status message")
    
    # Finalize
    history_file = logger.finalize()
    print(f"✓ Session finalized: {history_file}")
    
    # Verify file exists
    if Path(history_file).exists():
        size = Path(history_file).stat().st_size
        print(f"✓ History file created ({size} bytes)")
        return True
    else:
        print(f"✗ History file not created")
        return False


def test_face_lock_system():
    """Test FaceLockSystem initialization."""
    print("\n" + "="*80)
    print("TEST 7: FaceLockSystem Initialization")
    print("="*80)
    
    from src.face_lock import FaceLockSystem
    
    try:
        system = FaceLockSystem(
            db_path=Path("data/db/face_db.npz"),
            model_path="models/embedder_arcface.onnx",
            distance_threshold=0.34,
        )
        print("✓ FaceLockSystem initialized")
        print(f"  Database: {len(system.db_names)} enrolled faces")
        
        if system.db_names:
            print(f"  Available faces: {', '.join(system.db_names[:5])}")
            if len(system.db_names) > 5:
                print(f"    ... and {len(system.db_names) - 5} more")
        else:
            print("  ⚠ No enrolled faces found (run: python -m src.enroll)")
        
        return True
    except Exception as e:
        print(f"✗ FaceLockSystem initialization failed: {e}")
        return False


def test_file_structure():
    """Test database files."""
    print("\n" + "="*80)
    print("TEST 8: Database Files")
    print("="*80)
    
    npz_path = Path("data/db/face_db.npz")
    json_path = Path("data/db/face_db.json")
    
    if npz_path.exists():
        print(f"✓ face_db.npz found ({npz_path.stat().st_size} bytes)")
    else:
        print(f"⚠ face_db.npz not found (no enrollments yet)")
    
    if json_path.exists():
        print(f"✓ face_db.json found ({json_path.stat().st_size} bytes)")
    else:
        print(f"⚠ face_db.json not found (no enrollments yet)")
    
    # Check enrollment crops
    enroll_dir = Path("data/enroll")
    if enroll_dir.exists():
        enrolled_people = [d.name for d in enroll_dir.iterdir() if d.is_dir()]
        if enrolled_people:
            print(f"✓ {len(enrolled_people)} enrolled persons found:")
            for person in enrolled_people[:5]:
                crops = list((enroll_dir / person).glob("*.jpg"))
                print(f"    {person}: {len(crops)} crops")
        else:
            print(f"⚠ No enrolled persons (run: python -m src.enroll)")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("FACE LOCKING SYSTEM - COMPREHENSIVE TEST SUITE")
    print("="*80)
    
    tests = [
        ("Dependencies", test_imports),
        ("Project Modules", test_modules),
        ("Model File", test_model_file),
        ("Directories", test_directories),
        ("ActionDetector", test_action_detector),
        ("FaceHistoryLogger", test_history_logger),
        ("FaceLockSystem", test_face_lock_system),
        ("Database Files", test_file_structure),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n✗ {name} test crashed: {e}")
            results[name] = False
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {name}")
    
    print("-" * 80)
    print(f"Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED! System is ready to use.")
        print("\nNext step:")
        print("  python -m src.face_lock")
        return 0
    elif passed >= total - 2:
        print("\n⚠ Most tests passed, but check warnings above")
        print("\nCommon issues:")
        print("  - No enrolled faces: run 'python -m src.enroll'")
        print("  - Model not downloaded: see GUIDE.md")
        return 1
    else:
        print("\n✗ TESTS FAILED: Check errors above")
        print("\nSee GUIDE.md for detailed setup instructions")
        return 1


if __name__ == "__main__":
    sys.exit(main())
