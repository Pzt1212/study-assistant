@echo off
rem ============================================================
rem  学习助手 - 一键后台启动（start.bat）
rem  使用 pythonw.exe 后台运行（无黑色命令行窗口），
rem  日志写入 logs\app.log，PID 写入 logs\app.pid（供停止使用）
rem  停止：stop.bat / manage.py stop   查看状态：manage.py status
rem  监听地址/端口可用环境变量 APP_HOST / APP_PORT 覆盖
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0.."

if not exist logs mkdir logs

rem 定位 pythonw（后台运行，不弹黑色窗口）
set "PYW=%PYTHONW%"
if not defined PYW if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" set "PYW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if not defined PYW set "PYW=pythonw"

rem 日志与 PID 文件（本脚本约定 logs\app.log / logs\app.pid）
set "APP_LOG_FILE=logs\app.log"
set "APP_PID_FILE=logs\app.pid"
set "FLASK_DEBUG=0"

start "study-assistant-server" /B "%PYW%" "%~dp0..\tools\run_server.py"
echo 服务正在后台启动…
echo   日志：logs\app.log
echo   地址：http://127.0.0.1:%APP_PORT%   （默认 5000，可用 APP_PORT 覆盖）
echo.

rem 等待 3 秒后做一次健康检查
timeout /t 3 /nobreak >nul
set "PORT=%APP_PORT%"
if not defined PORT set "PORT=5000"
powershell -NoProfile -Command "$u='http://127.0.0.1:'+$env:PORT+'/api/health'; try { $r=Invoke-WebRequest -UseBasicParsing $u -TimeoutSec 3; Write-Host ('健康检查通过：HTTP ' + $r.StatusCode) } catch { Write-Host '健康检查未通过：服务可能仍在启动，请稍候运行 python manage.py status 查看' }"

echo.
echo 常用命令：
echo   python manage.py status    查看运行状态
echo   python manage.py log       查看最近日志
echo   stop.bat                   停止服务
echo.
