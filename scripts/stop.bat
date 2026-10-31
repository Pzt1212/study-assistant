@echo off
rem ============================================================
rem  学习助手 - 停止后台服务（stop.bat）
rem  1) 优先读取 logs\app.pid 停止服务
rem  2) 无 PID 文件时按端口（默认 5000 / APP_PORT 可覆盖）查找并结束进程
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0.."

set "PY=%PYTHON%"
if not defined PY if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
if not defined PY set "PY=python"

set "APP_PID_FILE=logs\app.pid"
set "PORT=%APP_PORT%"
if not defined PORT set "PORT=5000"

echo 停止学习助手服务（PID 文件优先，端口 %PORT% 兜底）…
"%PY%" "%~dp0..\tools\stop_server.py"
