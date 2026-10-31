@echo off
rem ============================================================
rem  Study Assistant - show Cloudflare Tunnel status
rem  process state + log tail + extracted public URL + health
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
set "PIDFILE=%~dp0tunnel\logs\tunnel.pid"
set "TLOG=%~dp0tunnel\logs"
set "OUTLOG=%TLOG%\tunnel.out.log"
set "ERRLOG=%TLOG%\tunnel.err.log"

echo ============================================================
echo  Study Assistant Tunnel status
echo ============================================================

powershell -NoProfile -Command "$pidf='%PIDFILE%'; $cfproc=Get-Process cloudflared -ErrorAction SilentlyContinue; $st='NOT RUNNING'; if(Test-Path $pidf){ $tp=(Get-Content $pidf -Raw).Trim(); if($tp -and (Get-Process -Id ([int]$tp) -ErrorAction SilentlyContinue)){ $st='RUNNING (PID='+$tp+')' } else { $st='PID stale, process exited ('+$tp+')' } } elseif($cfproc){ $st='RUNNING (cloudflared, no PID file)' }; Write-Host ('  status : '+$st)"

echo.
echo  ----- log tail -----
powershell -NoProfile -Command "$l=@(); if(Test-Path '%OUTLOG%'){$l+=Get-Content -LiteralPath '%OUTLOG%' -Tail 5}; if(Test-Path '%ERRLOG%'){$l+=Get-Content -LiteralPath '%ERRLOG%' -Tail 7}; if($l.Count){ $l | Select-Object -Last 9 | ForEach-Object { Write-Host $_ } } else { Write-Host '(no log yet - run tunnel_start.bat first)' }"

echo.
echo  ----- public URL -----
powershell -NoProfile -Command "$c=''; foreach($f in @('%OUTLOG%','%ERRLOG%')){ if(Test-Path $f){ $c += Get-Content -LiteralPath $f -Raw } }; $m=[regex]::Match($c,'https://[a-z0-9-]+\.trycloudflare\.com'); if($m.Success){ Write-Host ('  '+$m.Value) } else { Write-Host '  (not assigned yet - wait a moment or check log above)' }"

echo.
echo  ----- public health check -----
powershell -NoProfile -Command "$c=''; foreach($f in @('%OUTLOG%','%ERRLOG%')){ if(Test-Path $f){ $c += Get-Content -LiteralPath $f -Raw } }; $m=[regex]::Match($c,'https://[a-z0-9-]+\.trycloudflare\.com'); if($m.Success){ try { $r=Invoke-WebRequest -Uri ($m.Value + '/api/health') -TimeoutSec 12 -UseBasicParsing; Write-Host ('  '+$r.StatusCode+' OK') } catch { Write-Host '  unreachable - make sure local server (start_server.bat) is running' } } else { Write-Host '  n/a (no public URL yet)' }"

echo.
pause
