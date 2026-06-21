# Install Windows Task Scheduler job: tunnel check at logon + every 30 minutes.
# Run in PowerShell:  .\scripts\install-tunnel-task.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$AgentDir = Join-Path $env:APPDATA "ku-leuven-autobooker"
$TaskName = "ku-leuven-autobooker-tunnel"
$LogDir = Join-Path $env:LOCALAPPDATA "ku-leuven-autobooker"

New-Item -ItemType Directory -Force -Path $AgentDir, $LogDir, (Join-Path $AgentDir "lib") | Out-Null

Copy-Item (Join-Path $ScriptDir "tunnel-if-needed.ps1") (Join-Path $AgentDir "tunnel-if-needed.ps1") -Force
Copy-Item (Join-Path $ScriptDir "lib\local-env.ps1") (Join-Path $AgentDir "lib\local-env.ps1") -Force

$localEnv = Join-Path $RepoRoot "config\local.env"
if (Test-Path $localEnv) {
    Copy-Item $localEnv (Join-Path $AgentDir "local.env") -Force
} else {
    Write-Warning "config\local.env not found — copy config\local.env.example first."
}

$bookingJson = Join-Path $RepoRoot "config\booking.local.json"
if (Test-Path $bookingJson) {
    Copy-Item $bookingJson (Join-Path $AgentDir "booking.local.json") -Force
}

$runner = Join-Path $AgentDir "run-tunnel.ps1"
@'
$env:AUTBOOKER_AGENT_DIR = Join-Path $env:APPDATA "ku-leuven-autobooker"
& (Join-Path $env:AUTBOOKER_AGENT_DIR "tunnel-if-needed.ps1")
'@ | Set-Content -Path $runner -Encoding UTF8

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""

$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$repeatTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::MaxValue)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($logonTrigger, $repeatTrigger) `
    -Settings $settings -Principal $principal -Force | Out-Null

& $runner

Write-Host "Installed scheduled task: $TaskName"
Write-Host "  Agent files: $AgentDir"
Write-Host "  Runs at logon + every 30 min during active booking window"
Write-Host ""
Write-Host "After editing config\local.env, re-run this script to refresh the agent copy."
Write-Host "Remove task: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
