@echo off
rem ============================================================
rem  Study Assistant - stop Cloudflare Tunnel
rem  Stop by PID file first; fallback to process name
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
set "PIDFILE=%~dp0tunnel\logs\tunnel.pid"

if exist "%PIDFILE%" (
  for /f "usebackq delims=" %%p in ("%PIDFILE%") do (
    echo Stopping tunnel process PID=%%p ...
    taskkill /PID %%p /F /T >nul 2>nul
  )
  del "%PIDFILE%" >nul 2>nul
  echo Tunnel stopped.
  pause
  exit /b 0
)

echo No PID file found, stopping by process name cloudflared.exe ...
taskkill /IM cloudflared.exe /F >nul 2>nul
if errorlevel 1 (
  echo No cloudflared process running.
) else (
  echo cloudflared stopped.
)
pause
