@echo off
setlocal
title Optarb - Option Position Risk Monitor
cd /d "%~dp0"

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PY=C:\Users\milan\AppData\Local\Programs\Python\Python311\python.exe"
set "PORT=8104"
REM Sleep helper: ping-based, independent of PATH and safe with redirected stdin.
set "P1=%SystemRoot%\System32\ping.exe -n 2 127.0.0.1"
set "P2=%SystemRoot%\System32\ping.exe -n 3 127.0.0.1"
set "P3=%SystemRoot%\System32\ping.exe -n 4 127.0.0.1"

echo ================================================
echo   Optarb  -  Option Position Risk Monitor
echo   http://127.0.0.1:%PORT%
echo ================================================
echo.

if not exist "%PY%" (
    echo [X] Python not found:
    echo     %PY%
    echo     Edit this file and fix the PY path.
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%\src\backend\app.py" (
    echo [X] backend\app.py not found under:
    echo     %ROOT%
    echo.
    pause
    exit /b 1
)

netstat -ano | findstr "LISTENING" | findstr ":%PORT%" >nul
if not errorlevel 1 (
    echo [i] Server already running on port %PORT%.
    echo     Opening browser...
    start "" http://127.0.0.1:%PORT%
    %P2% >nul 2>&1
    exit /b 0
)

echo [1/3] Freeing port %PORT% ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":%PORT%"') do (
    echo       killing PID=%%p
    taskkill /PID %%p /F >nul 2>&1
)
%P1% >nul 2>&1

echo [2/3] Starting backend in a new window...
start "Optarb Backend" cmd /k "cd /d "%ROOT%\src" && set NO_PROXY=127.0.0.1,localhost,*.local && "%PY%" backend\app.py"

echo [3/3] Waiting for port %PORT% ...
set /a n=0
:wait
%P1% >nul 2>&1
netstat -ano | findstr "LISTENING" | findstr ":%PORT%" >nul
if not errorlevel 1 goto ok
set /a n+=1
if %n% lss 20 goto wait

echo.
echo [X] FAILED: port %PORT% not listening after 20s.
echo     Look at the "Optarb Backend" window for the traceback.
echo     Or run this manually to see the error:
echo     cd /d "%ROOT%\src" ^&^& "%PY%" backend\app.py
echo.
pause
exit /b 1

:ok
echo [OK] Server is up: http://127.0.0.1:%PORT%
echo      You may close this launcher window; the backend keeps running.
echo      To stop it later, run stop.bat
start "" http://127.0.0.1:%PORT%
%P3% >nul 2>&1
exit /b 0
