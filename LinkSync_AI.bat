@echo off
:: ============================================================
:: LinkSync AI — One-Click Launcher
:: ============================================================
:: Double-click this file to start LinkSync AI.
:: First run: auto-creates virtual environment & installs deps.
:: Subsequent runs: launches instantly in background.
:: ============================================================

title LinkSync AI — Starting...

:: Navigate to project directory
cd /d "%~dp0"

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+ from https://python.org
    echo Press any key to open the download page...
    pause >nul
    start https://www.python.org/downloads/
    exit /b 1
)

:: First-run: create virtual environment if it doesn't exist
if not exist ".venv\Scripts\python.exe" (
    echo [LinkSync AI] First-time setup — creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    
    echo [LinkSync AI] Installing dependencies...
    .venv\Scripts\pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    
    echo [LinkSync AI] Installing Playwright browser...
    .venv\Scripts\playwright install chromium
    if errorlevel 1 (
        echo [WARNING] Playwright install failed. Scraping may not work.
    )
    
    echo [LinkSync AI] Setup complete! Launching...
)

:: Launch the app silently (pythonw = no console window)
start "" /B .venv\Scripts\pythonw.exe main.py
exit
