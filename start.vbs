' ============================================================
'  学习助手 - 彻底静默启动（start.vbs）
'  双击本文件：完全不弹出任何窗口，后台启动服务
'  日志写入 logs\app.log，PID 写入 logs\app.pid
'  停止：stop.bat / python manage.py stop
'  状态：python manage.py status
' ============================================================
Option Explicit

Dim fso, shell, root, pyw, logFile, pidFile, port
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' 项目根目录（本文件所在目录）
root = fso.GetParentFolderName(WScript.ScriptFullName)

' 定位 pythonw.exe：环境变量 PYTHONW > AppData\Local\Python\bin\pythonw.exe > pythonw
pyw = shell.ExpandEnvironmentStrings("%PYTHONW%")
If Trim(pyw) = "" Or Not fso.FileExists(pyw) Then
    pyw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Python\bin\pythonw.exe"
End If
If Not fso.FileExists(pyw) Then pyw = "pythonw"

If Not fso.FolderExists(root & "\logs") Then fso.CreateFolder(root & "\logs")

' 通过进程级环境变量告知 run_server.py 使用 logs\app.log / logs\app.pid
shell.Environment("Process")("APP_LOG_FILE") = root & "\logs\app.log"
shell.Environment("Process")("APP_PID_FILE") = root & "\logs\app.pid"
shell.Environment("Process")("FLASK_DEBUG") = "0"

' 后台静默启动（窗口类型 0 = 完全隐藏）
shell.Run """" & pyw & """ """ & root & "\tools\run_server.py""", 0, False
