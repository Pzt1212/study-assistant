# Launch Quick or Named cloudflared tunnel in background for Study Assistant.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File tunnel\launch.ps1
$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$CF   = Join-Path $PSScriptRoot 'cloudflared.exe'
if (-not (Test-Path $CF)) { $CF = 'cloudflared' }
$LogDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$OutLog = Join-Path $LogDir 'tunnel.out.log'
$ErrLog = Join-Path $LogDir 'tunnel.err.log'
$PidFile = Join-Path $LogDir 'tunnel.pid'

if (Test-Path $PidFile) {
    Write-Host '[PID file exists - tunnel may already be running]'
    exit 1
}

$Domain = [Environment]::GetEnvironmentVariable('TUNNEL_DOMAIN')
if ([string]::IsNullOrWhiteSpace($Domain)) {
    Write-Host '[Quick Tunnel] requesting temporary hostname...'
    $argsList = @('tunnel', '--url', 'http://127.0.0.1:5000', '--no-autoupdate')
} else {
    Write-Host "[Named tunnel] domain: $Domain"
    # Delegate to Python launcher (does login-check, create, route, spawn)
    $Py = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $Py) { $Py = 'python' }
    $pyArgs = @((Join-Path $PSScriptRoot 'named_tunnel.py'))
    $env:TUNNEL_DOMAIN = $Domain
    $proc = Start-Process -FilePath $Py -ArgumentList $pyArgs -WorkingDirectory $Root -NoNewWindow -Wait -PassThru
    Write-Host "[python named launcher exit=$($proc.ExitCode)]"
    exit $proc.ExitCode
}

$proc = Start-Process -FilePath $CF -ArgumentList $argsList `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog `
    -WindowStyle Hidden -PassThru
$proc.Id | Out-File -FilePath $PidFile -Encoding ascii
Write-Host "[started cloudflared PID=$($proc.Id)]"
Write-Host "  log : $OutLog / $ErrLog"
Write-Host "  stop: tunnel_stop.bat   status: tunnel_status.bat"
