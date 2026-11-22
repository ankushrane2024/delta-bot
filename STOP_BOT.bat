@echo off
title Stop Delta BTC Options Bot
cd /d "%~dp0"

echo ===================================================
echo     DELTA BTC OPTIONS BOT - STOPPER
echo ===================================================
echo.

echo [*] Searching for processes on port 5000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000') do (
    echo [*] Terminating process PID %%a on port 5000...
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [OK] Bot server stopped successfully.
timeout /t 3
