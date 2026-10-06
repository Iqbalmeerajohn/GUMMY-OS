<#
.SYNOPSIS
    Bring the whole GUMMY stack up from a cold machine, in dependency order.

.DESCRIPTION
    Four processes have to start in the right order, and three of them fail
    confusingly if the one before is not ready yet:

      Docker Desktop  ->  Postgres  ->  migrations  ->  backend
      Ollama (independent)                          ->  frontend

    The backend will start against a database that is not listening and then
    fail every request; the frontend will start against a backend that is not
    there and show an empty shell. Both look like application bugs. So this
    script waits for each dependency to actually answer before starting the
    next thing, and says which one it is waiting on.

    Safe to run when things are already up: every step checks first, so a
    second run is a no-op plus a status report rather than a pile of duplicate
    processes.

.PARAMETER Stop
    Stop the backend and frontend (leaves Postgres and Ollama running).

.PARAMETER Rebuild
    Rebuild the frontend before starting it. Needed after pulling changes.

.PARAMETER Dev
    Run the frontend dev server instead of the production build. Slower and
    rebuilds constantly; use it when you are editing the UI.
#>

[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Rebuild,
    [switch]$Dev
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$LogDir = Join-Path $env:LOCALAPPDATA 'GummyOS\logs'

function Say($msg, $colour = 'Gray') { Write-Host "  $msg" -ForegroundColor $colour }
function Step($msg) { Write-Host "`n> $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "  [ok] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Die($msg) { Write-Host "`n  [x] $msg" -ForegroundColor Red; exit 1 }

function Invoke-Native {
    <#
        Run an external command and return @{ Code; Output } without letting
        its stderr become a PowerShell error.

        This exists because of a genuine Windows PowerShell trap: with
        $ErrorActionPreference = 'Stop', redirecting a native command's stderr
        into the PowerShell stream (`2>&1`) wraps each line in an ErrorRecord
        and terminates the script — even when the command succeeded. `docker
        compose up` writes its normal progress ("Network ... Creating") to
        stderr, so the happy path was killing the launcher.

        Native tools report success through the exit code. That is what we
        read; stderr is captured as plain text for diagnostics only.
    #>
    param([Parameter(Mandatory)][string]$Exe, [string[]]$Arguments = @())

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
        return @{ Code = $LASTEXITCODE; Output = $output }
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Test-Port([int]$Port) {
    # A TcpClient probe rather than Test-NetConnection: the cmdlet takes ~1s
    # per call even on a closed port, which makes a polling loop crawl.
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $ok = $client.ConnectAsync('127.0.0.1', $Port).Wait(400)
        $client.Close()
        return $ok
    } catch { return $false }
}

function Wait-Port([int]$Port, [string]$Name, [int]$TimeoutSeconds = 120) {
    if (Test-Port $Port) { Ok "$Name already listening on :$Port"; return $true }
    Say "waiting for $Name on :$Port ..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port $Port) { Ok "$Name is up on :$Port"; return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Start-Detached {
    # NOTE: the arguments parameter must NOT be called $Args. That name
    # collides with PowerShell's automatic $Args variable, which silently
    # arrives empty here and makes Start-Process reject -ArgumentList as null.
    param(
        [string]$Name,
        [string]$WorkingDir,
        [string]$Exe,
        [string[]]$CommandArgs
    )
    <#
        Detached, with output to a log file. A visible console window per
        service would be four windows to accidentally close; a log file
        survives and can be read after the fact.
    #>
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $log = Join-Path $LogDir "$Name.log"
    Start-Process -FilePath $Exe -ArgumentList $CommandArgs -WorkingDirectory $WorkingDir `
        -WindowStyle Hidden -RedirectStandardOutput $log `
        -RedirectStandardError (Join-Path $LogDir "$Name.err.log") | Out-Null
    Say "log: $log"
}

# ── stop ─────────────────────────────────────────────────────────────────────

if ($Stop) {
    Step 'Stopping GUMMY'
    # Stop by who is LISTENING on the port, not by matching a command line.
    # Command-line matching is fragile in exactly the case that matters: the
    # same process launched from bash, PowerShell or a scheduled task writes
    # its path with different slash directions, so a pattern that works for
    # one launcher silently matches nothing for another. The listening socket
    # is the same fact however the process was started.
    #
    # Killing every python.exe or node.exe would take unrelated work with it,
    # so the port is also the narrowest possible target.
    foreach ($svc in @(
        @{ Name = 'backend'; Port = 8000 }
        @{ Name = 'frontend'; Port = 3000 }
    )) {
        $owners = Get-NetTCPConnection -LocalPort $svc.Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        if (-not $owners) { Say "$($svc.Name): nothing listening on :$($svc.Port)"; continue }
        foreach ($processId in $owners) {
            $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
            # A dev server spawns workers; killing the tree avoids orphans that
            # keep the port bound and make the next start look like a conflict.
            Invoke-Native -Exe 'taskkill.exe' -Arguments @('/PID', "$processId", '/T', '/F') | Out-Null
            Ok "stopped $($svc.Name) (pid $processId$(if ($proc) { ", $($proc.ProcessName)" }))"
        }
    }
    Say 'Postgres and Ollama left running (cheap, and slow to restart).'
    Say 'Stop Postgres too with: docker compose down'
    exit 0
}

Write-Host ''
Write-Host '  GUMMY OS' -ForegroundColor Green
Write-Host '  Personal AI, on your own hardware.' -ForegroundColor DarkGray

# ── 0. prerequisites ─────────────────────────────────────────────────────────

Step 'Checking prerequisites'
if (-not (Test-Path $VenvPython)) {
    Die "backend venv missing. Run:  cd backend; uv sync --extra energy"
}
if (-not (Test-Path (Join-Path $BackendDir '.env'))) {
    Die "backend\.env missing. Run:  cd backend; copy .env.example .env"
}
if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Die "frontend deps missing. Run:  cd frontend; npm install"
}
Ok 'venv, .env and node_modules present'

# ── 1. Docker ────────────────────────────────────────────────────────────────

Step 'Docker'
$dockerUp = $false
$dockerUp = (Invoke-Native -Exe 'docker' -Arguments @('info')).Code -eq 0

if (-not $dockerUp) {
    $dd = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $dd)) { Die 'Docker Desktop is not installed, and Postgres runs in it.' }
    Say 'starting Docker Desktop (this is the slow part, ~30-60s) ...'
    Start-Process $dd | Out-Null
    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        if ((Invoke-Native -Exe 'docker' -Arguments @('info')).Code -eq 0) { $dockerUp = $true; break }
        Start-Sleep -Seconds 3
    }
    if (-not $dockerUp) { Die 'Docker Desktop did not become ready within 3 minutes.' }
}
Ok 'Docker engine is ready'

# ── 2. Postgres ──────────────────────────────────────────────────────────────

Step 'Postgres (pgvector)'
Push-Location $RepoRoot
$compose = Invoke-Native -Exe 'docker' -Arguments @('compose', 'up', '-d')
Pop-Location
if ($compose.Code -ne 0) {
    $compose.Output | Select-Object -Last 10 | ForEach-Object { Say $_ }
    Die 'docker compose up failed.'
}
if (-not (Wait-Port 5432 'Postgres' 90)) { Die 'Postgres never started. Check: docker compose logs db' }

# The port opening and the database accepting queries are not the same moment.
# Migrations run immediately after this, and they fail confusingly against a
# server that is still initialising.
Say 'waiting for Postgres to accept connections ...'
$deadline = (Get-Date).AddSeconds(60)
$ready = $false
while ((Get-Date) -lt $deadline) {
    $probe = Invoke-Native -Exe 'docker' -Arguments @('exec', 'gummy-db', 'pg_isready', '-U', 'gummy', '-d', 'gummy')
    if ($probe.Code -eq 0) { $ready = $true; break }
    Start-Sleep -Milliseconds 800
}
if (-not $ready) { Die 'Postgres is listening but not accepting connections.' }
Ok 'Postgres is accepting connections'

# ── 3. Migrations ────────────────────────────────────────────────────────────

Step 'Database schema'

# The head revision, read from the migration filenames rather than hardcoded,
# so this stays correct as migrations are added.
$MigrationsDir = Join-Path $BackendDir 'app\database\migrations\versions'
$headRevision = Get-ChildItem $MigrationsDir -Filter '*.py' -ErrorAction SilentlyContinue |
    Where-Object { $_.BaseName -match '^\d{4}_' } |
    Sort-Object BaseName | Select-Object -Last 1 -ExpandProperty BaseName

$applied = (Invoke-Native -Exe 'docker' -Arguments @(
    'exec', 'gummy-db', 'psql', '-U', 'gummy', '-d', 'gummy',
    '-tAc', 'select version_num from alembic_version'
)).Output -join '' -replace '\s', ''

Push-Location $BackendDir
try {
    $migrate = Invoke-Native -Exe $VenvPython -Arguments @('-m', 'alembic', 'upgrade', 'head')
    if ($migrate.Code -eq 0) {
        Ok 'schema is at head'
    }
    elseif ($headRevision -and $applied -eq $headRevision) {
        # Alembic could not run, but the database is already at the newest
        # revision this checkout contains — so there is nothing to apply and
        # starting is safe. Distinguishing these two cases matters: refusing
        # to start over a broken *tool* when the *schema* is fine would be a
        # false alarm, and applying nothing silently would be a real risk.
        Warn "the alembic CLI is broken in this venv, but the database is"
        Warn "already at $applied (head), so there is nothing to apply."
        Warn 'Repair when convenient:  reboot, then  cd backend; uv sync'
    }
    else {
        $migrate.Output | Select-Object -Last 12 | ForEach-Object { Say $_ }
        Say ''
        Say "database is at: $(if ($applied) { $applied } else { '(unknown)' })"
        Say "checkout head : $(if ($headRevision) { $headRevision } else { '(unknown)' })"
        Die 'Migrations failed and the schema is NOT current. Refusing to start.'
    }
} finally { Pop-Location }

# ── 4. Ollama ────────────────────────────────────────────────────────────────

Step 'Ollama (local model)'
if (-not (Test-Port 11434)) {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Die 'Ollama is not installed. GUMMY has no model to think with. https://ollama.com'
    }
    Say 'starting ollama serve ...'
    Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
    if (-not (Wait-Port 11434 'Ollama' 60)) { Die 'Ollama did not start.' }
} else { Ok 'Ollama already running on :11434' }

# A model that is not pulled fails on the first message, not at startup —
# which is the worst time to discover it.
$models = (Invoke-Native -Exe 'ollama' -Arguments @('list')).Output -join "`n"
foreach ($needed in @('qwen2.5:3b', 'nomic-embed-text')) {
    if ($models -notmatch [regex]::Escape($needed.Split(':')[0])) {
        Warn "model '$needed' is not pulled. Run:  ollama pull $needed"
    }
}

# ── 5. Backend ───────────────────────────────────────────────────────────────

Step 'Backend (API, workers, scheduler)'
if (Test-Port 8000) {
    Ok 'already running on :8000'
} else {
    Start-Detached -Name 'gummy-backend' -WorkingDir $BackendDir `
        -Exe $VenvPython -CommandArgs @('scripts/serve.py')
    if (-not (Wait-Port 8000 'Backend' 120)) {
        Die "Backend did not start. Check $LogDir\gummy-backend.err.log"
    }
}

# ── 6. Frontend ──────────────────────────────────────────────────────────────

Step 'Frontend'
if (Test-Port 3000) {
    Ok 'already running on :3000'
} else {
    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
    if (-not $npm) { Die 'npm is not on PATH.' }

    if ($Rebuild -or (-not $Dev -and -not (Test-Path (Join-Path $FrontendDir '.next\BUILD_ID')))) {
        Say 'building the frontend (one-off, ~1-2 min) ...'
        Push-Location $FrontendDir
        try {
            $build = Invoke-Native -Exe $npm.Source -Arguments @('run', 'build')
            if ($build.Code -ne 0) {
                $build.Output | Select-Object -Last 12 | ForEach-Object { Say $_ }
                Die 'Frontend build failed.'
            }
        } finally { Pop-Location }
        Ok 'built'
    }

    $script = if ($Dev) { 'dev' } else { 'start' }
    Start-Detached -Name 'gummy-frontend' -WorkingDir $FrontendDir `
        -Exe $npm.Source -CommandArgs @('run', $script)
    if (-not (Wait-Port 3000 'Frontend' 120)) {
        Die "Frontend did not start. Check $LogDir\gummy-frontend.err.log"
    }
}

# ── done ─────────────────────────────────────────────────────────────────────

# A bound port is not a ready app: uvicorn listens before the routes are
# mounted, so the first probe can lose a race it is not really losing. Retry
# briefly rather than reporting a healthy backend as unreachable.
$health = 'unreachable'
foreach ($attempt in 1..10) {
    try {
        $health = (Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 4).status
        break
    } catch { Start-Sleep -Milliseconds 800 }
}

# ASCII only. The console here is not UTF-8 by default, and box-drawing
# characters arrive as mojibake, which makes a success banner look broken.
Write-Host ''
Write-Host '  ---------------------------------------------' -ForegroundColor DarkGray
Write-Host '   GUMMY is up' -ForegroundColor Green
Write-Host '  ---------------------------------------------' -ForegroundColor DarkGray
Write-Host ''
Write-Host '   App        http://localhost:3000' -ForegroundColor White
Write-Host '   API        http://localhost:8000' -ForegroundColor Gray
Write-Host '   API docs   http://localhost:8000/docs' -ForegroundColor Gray
Write-Host '   Health     http://localhost:8000/health' -ForegroundColor Gray
Write-Host ''
Write-Host "   backend health: $health" -ForegroundColor DarkGray
Write-Host "   logs: $LogDir" -ForegroundColor DarkGray
Write-Host ''
Write-Host '   stop with:  gummy stop' -ForegroundColor DarkGray
Write-Host ''

try { Start-Process 'http://localhost:3000' | Out-Null } catch {}
