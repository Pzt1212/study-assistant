@echo off
rem ============================================================
rem  学习助手 - 查看后台服务状态（含健康检查）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%PYTHON%"
if not defined PY if exist "%LOCALAPPDATA%\Local\Python\bin\python.exe" set "PY=%LOCALAPPDATA%\Local\Python\bin\python.exe"
if not defined PY set "PY=python"

"%PY%" "%~dp0tools\status_server.py"
pause
