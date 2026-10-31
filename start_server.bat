@echo off
rem ============================================================
rem  学习助手 - 一键后台启动
rem  双击本文件即以后台方式启动服务（无黑色窗口、日志写 logs\server.log）
rem  停止：双击 stop_server.bat   查看状态：双击 status_server.bat
rem  监听地址/端口可用环境变量 APP_HOST / APP_PORT 覆盖
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

rem 定位 pythonw（后台运行，不弹黑色窗口）
set "PYW=%PYTHONW%"
if not defined PYW if exist "%LOCALAPPDATA%\Local\Python\bin\pythonw.exe" set "PYW=%LOCALAPPDATA%\Local\Python\bin\pythonw.exe"
if not defined PYW set "PYW=pythonw"

start "" "%PYW%" "%~dp0tools\run_server.py"
echo 服务正在后台启动，日志：logs\server.log

rem 等待 2 秒后做一次健康检查
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "$u='http://127.0.0.1:5000/api/health'; try { $r=Invoke-WebRequest -UseBasicParsing $u -TimeoutSec 3; Write-Host ('健康检查通过：HTTP ' + $r.StatusCode) } catch { Write-Host '健康检查未通过（稍等后运行 status_server.bat 再看）' }"

echo.
echo 浏览器访问：http://127.0.0.1:5000
pause
