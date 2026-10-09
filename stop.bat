@echo off
setlocal
title Optarb - Stop Server
cd /d "%~dp0"

set "PORT=8104"
set "P1=%SystemRoot%\System32\ping.exe -n 2 127.0.0.1"

echo ================================================
echo   Stopping Optarb server (port %PORT%)
echo ================================================
echo.

set "FOUND="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":%PORT%"') do (
    echo   Killing PID=%%p
    taskkill /PID %%p /F >nul 2>&1
    set "FOUND=1"
)

%P1% >nul 2>&1
netstat -ano | findstr "LISTENING" | findstr ":%PORT%" >nul
if not errorlevel 1 (
    echo [X] Port %PORT% is still occupied. Kill it from Task Manager.
) else (
    if defined FOUND (
        echo [OK] Server stopped.
    ) else (
        echo [i] Nothing was listening on port %PORT%.
    )
)
echo.
pause
