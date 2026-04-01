#!/usr/bin/env python3
"""
Hand Tracker Application Launcher
Starts the hand tracker application on Windows, Mac, or Raspberry Pi
"""

import os
import sys
import subprocess
import platform

def main():
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Determine the Python executable path
    system = platform.system()
    
    if system == "Windows":
        # On Windows, use the venv Scripts directory
        python_exe = os.path.join(script_dir, "venv", "Scripts", "python.exe")
    else:
        # On Linux/Raspberry Pi/Mac, use the venv bin directory
        python_exe = os.path.join(script_dir, "venv", "bin", "python")
    
    # Check if virtual environment exists
    if not os.path.exists(python_exe):
        print(f"❌ Virtual environment not found at {python_exe}")
        print("Please create a virtual environment first:")
        print("  python -m venv venv")
        sys.exit(1)
    
    # Run the application
    app_script = os.path.join(script_dir, "Simple-Hand-Tracker.py")
    print(f"🦋 Starting Hand Tracker...")
    
    try:
        subprocess.run([python_exe, app_script], check=True)
    except KeyboardInterrupt:
        print("\n👋 Application closed")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
