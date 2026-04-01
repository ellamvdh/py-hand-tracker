@echo off
REM Hand Tracker Application Launcher for Windows
REM Double-click this file to start the application

cd /d "%~dp0"

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run the application
python Simple-Hand-Tracker.py

pause
