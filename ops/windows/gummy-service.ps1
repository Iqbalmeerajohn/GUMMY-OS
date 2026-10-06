<#
.SYNOPSIS
    Run GUMMY continuously on Windows via Scheduled Tasks.

.DESCRIPTION
    Registers the three long-lived processes GUMMY needs as per-user scheduled
    tasks that start at logon and restart on failure:

      GummyOS-Ollama    the local model server
      GummyOS-Backend   the FastAPI app (which owns the workers)
      GummyOS-Frontend  the Next.js UI

    Postgres is deliberately NOT a task here. It runs in Docker with
    `restart: unless-stopped`, so Docker Desktop already restarts it — adding a
    second supervisor would mean two things racing to start the same container.

    Why Scheduled Tasks rather than a Windows Service: a real service runs in
    session 0 with no user profile, and both Ollama (GPU access, model cache in
    the user profile) and the app's own `.env` and venv are per-user. A logon
    task keeps everything in the profile it was installed against, which is the
    thing that actually works without a lot of ceremony.

    Nothing here needs administrator rights, because nothing here is
    machine-wide.

.PARAMETER Action
    install | uninstall | status | start | stop

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File ops\windows\gummy-service.ps1 install
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('install', 'uninstall', 'status', 'start', 'stop')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

# Repository root, derived from this script's location so the task definitions
# keep working if the checkout moves.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$LogDir = Join-Path $env:LOCALAPPDATA 'GummyOS\logs'

$Tasks = @(
    @{ Name = 'GummyOS-Ollama';   Description = 'GUMMY: local model server' }
    @{ Name = 'GummyOS-Backend';  Description = 'GUMMY: API, workers, scheduler' }
    @{ Name = 'GummyOS-Frontend'; Description = 'GUMMY: web UI' }
)

function Write-Step($message) { Write-Host "  $message" -ForegroundColor Cyan }
function Write-Ok($message)   { Write-Host "  $message" -ForegroundColor Green }
function Write-Warn($message) { Write-Host "  $message" -ForegroundColor Yellow }

function Assert-Prerequisites {
    $missing = @()
    foreach ($cmd in 'ollama', 'npm', 'docker') {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { $missing += $cmd }
    }
    $venvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        $missing += 'backend\.venv (run: cd backend; uv sync)'
    }
    if (-not (Test-Path (Join-Path $BackendDir '.env'))) {
        $missing += 'backend\.env (copy from .env.example)'
    }
    if ($missing.Count -gt 0) {
        throw "Missing prerequisites:`n    - " + ($missing -join "`n    - ")
    }
}

function New-Runner {
    <#
        Each service gets a tiny .cmd wrapper rather than being invoked
        directly. Scheduled Tasks has no concept of "restart if the process
        exits cleanly but wrongly", and no log redirection at all — the wrapper
        gives us both, and makes the task definition trivial to read.
    #>
    param([string]$Name, [string]$WorkingDir, [string]$Command)

    $runnerDir = Join-Path $env:LOCALAPPDATA 'GummyOS\bin'
    New-Item -ItemType Directory -Force -Path $runnerDir, $LogDir | Out-Null
    $runner = Join-Path $runnerDir "$Name.cmd"

    # The loop is the supervisor: if the process exits for any reason, wait a
    # few seconds and start it again. The delay stops a fast-failing process
    # (bad .env, port already taken) from spinning the CPU.
    @"
@echo off
title $Name
cd /d "$WorkingDir"
:loop
echo [%date% %time%] starting $Name >> "$LogDir\$Name.log"
$Command >> "$LogDir\$Name.log" 2>&1
echo [%date% %time%] $Name exited with %errorlevel%, restarting in 10s >> "$LogDir\$Name.log"
timeout /t 10 /nobreak > nul
goto loop
"@ | Set-Content -Path $runner -Encoding ASCII

    return $runner
}

function Install-Tasks {
    Assert-Prerequisites
    Write-Step "Repository: $RepoRoot"
    Write-Step "Logs:       $LogDir"

    $venvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
    $runners = @{
        'GummyOS-Ollama'   = New-Runner -Name 'GummyOS-Ollama' -WorkingDir $RepoRoot `
            -Command 'ollama serve'
        'GummyOS-Backend'  = New-Runner -Name 'GummyOS-Backend' -WorkingDir $BackendDir `
            -Command "`"$venvPython`" scripts\serve.py"
        'GummyOS-Frontend' = New-Runner -Name 'GummyOS-Frontend' -WorkingDir $FrontendDir `
            -Command 'npm run start'
    }

    foreach ($task in $Tasks) {
        $name = $task.Name
        $action = New-ScheduledTaskAction -Execute 'cmd.exe' `
            -Argument "/c `"$($runners[$name])`""

        # Two triggers: at logon for the normal case, and at task-registration
        # time so `install` does not require a reboot to take effect.
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

        # Hidden windows, and no battery conditions: a laptop on battery should
        # still answer a message from your phone.
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -RestartCount 999 `
            -RestartInterval (New-TimeSpan -Minutes 1) `
            -ExecutionTimeLimit ([TimeSpan]::Zero) `
            -MultipleInstances IgnoreNew
        $settings.Hidden = $true

        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
        Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
            -Settings $settings -Description $task.Description | Out-Null
        Write-Ok "registered $name"
    }

    Write-Host ''
    Write-Warn 'The backend and frontend need Postgres, which runs in Docker:'
    Write-Warn '  docker compose up -d      (and enable "Start Docker Desktop when you log in")'
    Write-Warn 'Serve the frontend build, not the dev server:'
    Write-Warn '  cd frontend; npm run build'
    Write-Host ''
    Write-Step "Start now with: $PSCommandPath start"
}

function Uninstall-Tasks {
    foreach ($task in $Tasks) {
        if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
            Write-Ok "removed $($task.Name)"
        }
    }
    Write-Step "Logs left in place at $LogDir"
}

function Start-Tasks {
    foreach ($task in $Tasks) {
        Start-ScheduledTask -TaskName $task.Name -ErrorAction Stop
        Write-Ok "started $($task.Name)"
    }
}

function Stop-Tasks {
    foreach ($task in $Tasks) {
        Stop-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
        Write-Ok "stopped $($task.Name)"
    }
    Write-Warn 'The supervisor loop restarts on exit; use uninstall to stop for good.'
}

function Get-Status {
    Write-Host ''
    foreach ($task in $Tasks) {
        $registered = Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
        if (-not $registered) {
            Write-Warn "$($task.Name): not installed"
            continue
        }
        $info = Get-ScheduledTaskInfo -TaskName $task.Name
        Write-Host ("  {0,-20} {1,-10} last run {2}" -f `
            $task.Name, $registered.State, $info.LastRunTime) -ForegroundColor Gray
    }

    Write-Host ''
    foreach ($probe in @(
        @{ Name = 'Postgres'; Uri = $null;                            Port = 5432 }
        @{ Name = 'Ollama';   Uri = 'http://127.0.0.1:11434/api/tags'; Port = 11434 }
        @{ Name = 'Backend';  Uri = 'http://127.0.0.1:8000/health';    Port = 8000 }
        @{ Name = 'Frontend'; Uri = 'http://127.0.0.1:3000';           Port = 3000 }
    )) {
        $up = Test-NetConnection -ComputerName 127.0.0.1 -Port $probe.Port `
            -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($up) { Write-Ok "$($probe.Name) is up on :$($probe.Port)" }
        else     { Write-Warn "$($probe.Name) is DOWN on :$($probe.Port)" }
    }
    Write-Host ''
    Write-Step "Logs: $LogDir"
}

switch ($Action) {
    'install'   { Install-Tasks }
    'uninstall' { Uninstall-Tasks }
    'start'     { Start-Tasks }
    'stop'      { Stop-Tasks }
    default     { Get-Status }
}
