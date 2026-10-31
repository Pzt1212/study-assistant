@echo off
rem ============================================================
rem  学习助手 - 停止后台服务
rem  读取 logs\server.pid 终止对应进程并清理
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0.."

set "PY=%PYTHON%"
if not defined PY if exist "%LOCALAPPDATA%\Local\Python\bin\python.exe" set "PY=%LOCALAPPDATA%\Local\Python\bin\python.exe"
if not defined PY set "PY=python"

"%PY%" "%~dp0..\tools\stop_server.py"
pause
