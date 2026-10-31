' ============================================================
'  学习助手 - 静默启动备用脚本（start_silent.vbs）
'  与 start.vbs 效果一致：完全隐藏窗口后台启动服务；
'  本脚本作为「更彻底静默」的备用入口（无可视化任何输出）。
'  日志：logs\app.log   停止：stop.bat / manage.py stop
' ============================================================
Option Explicit

Dim fso, shell, root, pyw
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = shell.ExpandEnvironmentStrings("%PYTHONW%")
If Trim(pyw) = "" Or Not fso.FileExists(pyw) Then
    pyw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Python\bin\pythonw.exe"
End If
If Not fso.FileExists(pyw) Then pyw = "pythonw"

If Not fso.FolderExists(root & "\logs") Then fso.CreateFolder(root & "\logs")

shell.Environment("Process")("APP_LOG_FILE") = root & "\logs\app.log"
shell.Environment("Process")("APP_PID_FILE") = root & "\logs\app.pid"
shell.Environment("Process")("FLASK_DEBUG") = "0"

' 窗口类型 0：完全隐藏
shell.Run """" & pyw & """ """ & root & "\tools\run_server.py""", 0, False
