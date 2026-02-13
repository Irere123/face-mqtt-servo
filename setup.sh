#!/bin/bash
# setup.sh
# Quick setup script for Face Locking system

set -e  # Exit on error

echo "================================================================================"
echo "Face Locking System - Automated Setup"
echo "================================================================================"
echo

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
REQUIRED_VERSION="3.9"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}✗ Python 3.9+ required, found $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"
echo

# Create virtual environment
echo "Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${YELLOW}⚠ Virtual environment already exists${NC}"
fi
echo

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo -e "${GREEN}✓ pip upgraded${NC}"
echo

# Install dependencies
echo "Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt > /dev/null 2>&1
    echo -e "${GREEN}✓ Dependencies installed from requirements.txt${NC}"
else
    echo "Installing packages manually (no requirements.txt found)..."
    pip install opencv-python numpy onnxruntime scipy tqdm mediapipe protobuf > /dev/null 2>&1
    echo -e "${GREEN}✓ Dependencies installed${NC}"
fi
echo

# Check model
echo "Checking ArcFace model..."
if [ ! -f "models/embedder_arcface.onnx" ]; then
    echo -e "${YELLOW}⚠ Model not found. Downloading...${NC}"
    
    # Download
    echo "  Downloading buffalo_l.zip..."
    curl -L -o buffalo_l.zip "https://sourceforge.net/projects/insightface.mirror/files/v0.7/buffalo_l.zip/download" 2>/dev/null
    
    # Extract
    echo "  Extracting..."
    unzip -o buffalo_l.zip > /dev/null 2>&1
    
    # Copy
    mkdir -p models
    cp w600k_r50.onnx models/embedder_arcface.onnx
    
    # Cleanup
    rm -f buffalo_l.zip w600k_r50.onnx 1k3d68.onnx 2d106det.onnx det_10g.onnx genderage.onnx
    
    echo -e "${GREEN}✓ Model downloaded and installed${NC}"
else
    SIZE=$(du -h models/embedder_arcface.onnx | cut -f1)
    echo -e "${GREEN}✓ Model found ($SIZE)${NC}"
fi
echo

# Create directories
echo "Creating directories..."
mkdir -p data/db
mkdir -p data/enroll
mkdir -p data/face_histories
echo -e "${GREEN}✓ Directories created${NC}"
echo

# Run tests
echo "Running verification tests..."
python -m src.test_face_locking
TEST_RESULT=$?
echo

if [ $TEST_RESULT -eq 0 ]; then
    echo "================================================================================"
    echo -e "${GREEN}✓ SETUP COMPLETE!${NC}"
    echo "================================================================================"
    echo
    echo "Next steps:"
    echo "  1. Enroll faces:      python -m src.enroll"
    echo "  2. Evaluate threshold: python -m src.evaluate"
    echo "  3. Start face locking: python -m src.face_lock"
    echo
    echo "For detailed documentation, see:"
    echo "  - README.md"
    echo "  - FACE_LOCKING_GUIDE.md"
    echo "  - GUIDE.md"
    echo
else
    echo "================================================================================"
    echo -e "${RED}✗ Setup completed with warnings${NC}"
    echo "================================================================================"
    echo "Please check the test output above and install missing components."
    echo "See GUIDE.md for detailed troubleshooting."
    echo
fi

echo "To activate the environment in future sessions, run:"
echo "  source .venv/bin/activate"
echo
