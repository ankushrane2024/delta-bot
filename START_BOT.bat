@echo off
title Delta BTC Options Bot Launcher
cd /d "%~dp0"

echo ===================================================
echo     DELTA BTC OPTIONS BOT - LAUNCHER
echo ===================================================
echo.

:: 1. Check if server is already running on port 5000
netstat -ano | findstr :5000 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Bot web server is already running on port 5000!
    echo Opening dashboard in your browser...
    start http://localhost:5000
    timeout /t 3 >nul
    exit /b 0
)

:: 2. Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found in PATH!
    echo Please ensure Python 3.11+ is installed.
    pause
    exit /b 1
)

echo [*] Starting Delta BTC Options Bot (main.py)...
start "Delta BTC Options Bot Server" cmd /k "python main.py"

echo [*] Waiting for server to initialize...
timeout /t 5 >nul

echo [*] Opening Dashboard at http://localhost:5000...
start http://localhost:5000

echo.
echo ===================================================
echo   SUCCESS: Bot is active and dashboard is open!
echo   Keep the server window open while trading.
echo ===================================================
timeout /t 5
