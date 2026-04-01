#!/bin/bash

# Hand Tracker autostart script voor Raspberry Pi

# Pad naar het project
PROJECT_DIR="/home/pi/py-hand-tracker"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"

# Controleer of virtual environment bestaat
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment niet gevonden. Creating..."
    cd "$PROJECT_DIR"
    python3 -m venv venv
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -r requirements.txt
fi

# Controleer of afbeeldingen bestaan
if [ ! -f "$PROJECT_DIR/daisy.png" ] || [ ! -f "$PROJECT_DIR/background.png" ]; then
    echo "Waarschuwing: daisy.png of background.png ontbreekt!"
fi

# Start het programma
cd "$PROJECT_DIR"
exec "$PYTHON" Simple-Hand-Tracker.py
