function Import-AutobookerLocalEnv {
    param(
        [string]$RepoRoot,
        [string]$AgentDir = $env:AUTBOOKER_AGENT_DIR
    )

    $candidates = @()
    if ($AgentDir -and (Test-Path (Join-Path $AgentDir "local.env"))) {
        $candidates += (Join-Path $AgentDir "local.env")
    }
    if ($RepoRoot -and (Test-Path (Join-Path $RepoRoot "config\local.env"))) {
        $candidates += (Join-Path $RepoRoot "config\local.env")
    }

    foreach ($path in $candidates | Select-Object -Unique) {
        Get-Content $path | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#")) { return }
            $eq = $line.IndexOf("=")
            if ($eq -lt 1) { return }
            $name = $line.Substring(0, $eq).Trim()
            $value = $line.Substring($eq + 1).Trim()
            $value = $value.Replace('$HOME', $env:USERPROFILE).Replace('~', $env:USERPROFILE)
            Set-Item -Path "env:$name" -Value $value
        }
        return
    }
}

function Get-AutobookerBookingConfigPath {
    param(
        [string]$RepoRoot,
        [string]$AgentDir = $env:AUTBOOKER_AGENT_DIR
    )

    if ($AgentDir -and (Test-Path (Join-Path $AgentDir "booking.local.json"))) {
        return (Join-Path $AgentDir "booking.local.json")
    }
    if ($RepoRoot) {
        return (Join-Path $RepoRoot "config\booking.local.json")
    }
    return $null
}
