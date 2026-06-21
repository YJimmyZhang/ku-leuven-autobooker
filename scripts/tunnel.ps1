# Manual SSH tunnel (Windows). Keep this window open while sending cookies on KU campus WiFi.
# Requires OpenSSH client (Windows 10+): Settings → Apps → Optional features → OpenSSH Client

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
. (Join-Path $ScriptDir "lib\local-env.ps1")

Import-AutobookerLocalEnv -RepoRoot $RepoRoot

$serverIp = if ($env:DROPLET_IP) { $env:DROPLET_IP } elseif ($env:SERVER_IP) { $env:SERVER_IP } else { "YOUR_SERVER_IP" }
$sshKey = if ($env:SSH_KEY) { $env:SSH_KEY.Replace('$HOME', $env:USERPROFILE).Replace('~', $env:USERPROFILE) } else { Join-Path $env:USERPROFILE ".ssh\id_ed25519_do" }

Write-Host "Forwarding localhost:8080 → ${serverIp}:8080 (Ctrl+C to stop)"
& ssh -i $sshKey -N -L 127.0.0.1:8080:127.0.0.1:8080 "root@${serverIp}"
