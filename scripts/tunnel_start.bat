@echo off
rem ============================================================
rem  Study Assistant - Cloudflare Tunnel one-click start
rem  Default : Quick Tunnel (temporary *.trycloudflare.com)
rem  Custom domain: set TUNNEL_DOMAIN=your.domain then run
rem  Logs: tunnel\logs\  PID: tunnel\logs\tunnel.pid
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

if not exist "%~dp0tunnel\cloudflared.exe" (
  where cloudflared >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] cloudflared not found. Put cloudflared.exe into tunnel\ or add it to PATH.
    pause
    exit /b 1
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tunnel\launch.ps1"

echo.
echo  Tunnel started in background.
echo    - status / public URL : tunnel_status.bat
echo    - stop                : tunnel_stop.bat
timeout /t 2 /nobreak >nul
