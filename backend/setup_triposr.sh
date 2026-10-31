#!/usr/bin/env bash
set -euo pipefail

# Run from the repository root. Install the CUDA-compatible PyTorch build first
# using https://pytorch.org/get-started/locally/ for your machine.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$ROOT_DIR/backend/vendor"
TRIPOSR_DIR="$VENDOR_DIR/TripoSR"

mkdir -p "$VENDOR_DIR"
if [[ ! -d "$TRIPOSR_DIR/.git" ]]; then
  git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git "$TRIPOSR_DIR"
else
  echo "Using existing TripoSR checkout at $TRIPOSR_DIR"
fi

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r "$ROOT_DIR/requirements.txt"
python -m pip install -r "$TRIPOSR_DIR/requirements.txt"

echo
echo "TripoSR source and dependencies installed."
echo "Start the backend from backend/: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
