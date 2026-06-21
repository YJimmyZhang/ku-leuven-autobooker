# Starts SSH tunnel only during the configured booking period (Windows).
# Used by Task Scheduler via install-tunnel-task.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = if ($env:AUTBOOKER_AGENT_DIR) { $null } else { Split-Path -Parent $ScriptDir }

. (Join-Path $ScriptDir "lib\local-env.ps1")
Import-AutobookerLocalEnv -RepoRoot $RepoRoot

$serverIp = if ($env:DROPLET_IP) { $env:DROPLET_IP } elseif ($env:SERVER_IP) { $env:SERVER_IP } else { "YOUR_SERVER_IP" }
$sshKey = if ($env:SSH_KEY) { $env:SSH_KEY } else { Join-Path $env:USERPROFILE ".ssh\id_ed25519_do" }
$localPort = if ($env:LOCAL_PORT) { $env:LOCAL_PORT } else { "8080" }
$bookingConfig = Get-AutobookerBookingConfigPath -RepoRoot $RepoRoot
$tunnelPattern = "127.0.0.1:${localPort}:127.0.0.1:8080"

function Test-TunnelRunning {
    Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*${tunnelPattern}*" } |
        Select-Object -First 1
}

function Stop-TunnelIfRunning {
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*${tunnelPattern}*" }
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($procs) {
        Write-Host "[tunnel] Stopped (outside booking period or disabled)."
    }
}

function Test-NeedsTunnel {
    $healthUrl = "http://${serverIp}:8080/health"
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 4 -UseBasicParsing
        $d = $resp.Content | ConvertFrom-Json
        return [bool]($d.booking_enabled -and $d.booking_active_today)
    } catch {
        # fall through to local JSON
    }

    if (-not $bookingConfig -or -not (Test-Path $bookingConfig)) {
        return $false
    }

    $c = Get-Content $bookingConfig -Raw | ConvertFrom-Json
    if (-not $c.booking_enabled) { return $false }

    $today = Get-Date
    $offsetDays = if ($c.booking_date_offset_days) { [int]$c.booking_date_offset_days } else { 8 }
    $seatStart = [datetime]::Parse(($c.booking_period_start.ToString()).Substring(0, 10))
    $seatEnd = [datetime]::Parse(($c.booking_period_end.ToString()).Substring(0, 10))
    $runStart = $seatStart.AddDays(-$offsetDays)
    $runEnd = $seatEnd.AddDays(-$offsetDays)
    return ($today -ge $runStart -and $today -le $runEnd)
}

function Start-Tunnel {
    if (Test-TunnelRunning) {
        Write-Host "[tunnel] Already running on localhost:${localPort}"
        return
    }
    Write-Host "[tunnel] Starting → localhost:${localPort} (booking period active)"
    Start-Process -FilePath "ssh" -ArgumentList @(
        "-i", $sshKey,
        "-N",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=3",
        "-L", "127.0.0.1:${localPort}:127.0.0.1:8080",
        "root@${serverIp}"
    ) -WindowStyle Hidden
}

if (Test-NeedsTunnel) {
    Start-Tunnel
} else {
    Stop-TunnelIfRunning
    Write-Host "[tunnel] Not needed today — booking period inactive or disabled."
}
