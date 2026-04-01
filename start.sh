#!/bin/bash

# Hand Tracker Application Launcher
# This script starts the hand tracker application on Raspberry Pi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the application directory
cd "$SCRIPT_DIR"

# Activate the virtual environment
source venv/bin/activate

# Run the application
python Simple-Hand-Tracker.py

# Deactivate the virtual environment when done
deactivate
