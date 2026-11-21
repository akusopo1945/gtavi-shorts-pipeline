#!/usr/bin/env bash
set -e

echo "=== Setting up GTA Shorts Pipeline Environment ==="

# 1. System packages
if command -v apt-get &> /dev/null; then
    echo "[*] Installing system dependencies (ffmpeg, libass, fontconfig)..."
    sudo apt-get update -y || apt-get update -y || true
    sudo apt-get install -y ffmpeg libass-dev fontconfig fonts-dejavu-core python3-pip python3-venv || \
         apt-get install -y ffmpeg libass-dev fontconfig fonts-dejavu-core python3-pip python3-venv || true
fi

# 2. Fonts installation
echo "[*] Installing project fonts to user font directory..."
FONT_DIR="$HOME/.local/share/fonts"
mkdir -p "$FONT_DIR"
if [ -d "./assets/fonts" ]; then
    cp -r ./assets/fonts/* "$FONT_DIR/" 2>/dev/null || true
    fc-cache -f "$FONT_DIR" 2>/dev/null || true
fi

# 3. Python environment
echo "[*] Setting up Python virtual environment..."
if [ ! -d "./venv" ]; then
    python3 -m venv ./venv
fi

source ./venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Setup Completed Successfully! ==="
echo "Run engine using: ./venv/bin/python engine/clipper.py --help"
