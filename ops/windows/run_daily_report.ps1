[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet('OBSERVATION_ONLY', 'CANDIDATE_REPLAY')][string]$Mode = 'OBSERVATION_ONLY',
    [string]$RunDirectory,
    [string]$OutputDirectory,
    [int]$ActiveRuntimeWaitSeconds = 120
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$sourceRootCandidate = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$repository = if (Test-Path -LiteralPath (Join-Path $sourceRootCandidate 'pyproject.toml') -PathType Leaf) {
    $sourceRootCandidate
} else {
    $PSScriptRoot
}
$processHelper = Join-Path $PSScriptRoot 'lib\runtime_process.ps1'
if (-not $WhatIfPreference -and (Test-Path -LiteralPath $processHelper -PathType Leaf)) { . $processHelper }

function Get-MsoLatestCompletedRun {
    $roots = @(
        (Join-Path $runtimeRoot 'observations\rehearsals'),
        (Join-Path $runtimeRoot 'data_shadow')
    )
    $candidates = @()
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        $candidates += Get-ChildItem -LiteralPath $root -Filter 'RUN.json' -File -Recurse |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.Directory.FullName 'quality\DATA_QUALITY.json') -PathType Leaf }
    }
    return $candidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
}

function Test-MsoXnysSession {
    param([Parameter(Mandatory = $true)][string]$Python, [Parameter(Mandatory = $true)][string]$TradingDate)
    $code = "from datetime import date; from market_state_observatory.runtime.market_calendar import is_trading_day; raise SystemExit(0 if is_trading_day(date.fromisoformat('$TradingDate')) else 3)"
    & $Python -I -c $code
    return $LASTEXITCODE -eq 0
}

$deadline = (Get-Date).AddSeconds($ActiveRuntimeWaitSeconds)
do {
    $active = @()
    if (Get-Command Get-MsoLiveOwnedProcesses -ErrorAction SilentlyContinue) {
        $active = @(Get-MsoLiveOwnedProcesses -RuntimeRoot $runtimeRoot)
    }
    if ($active.Count -eq 0) { break }
    if ((Get-Date) -ge $deadline) { throw 'DAILY_REPORT_BLOCKED: capture runtime remained active past the bounded wait.' }
    Start-Sleep -Seconds 5
} while ($true)

$runFile = if ($RunDirectory) {
    Get-Item -LiteralPath (Join-Path $RunDirectory 'RUN.json') -ErrorAction Stop
} else {
    Get-MsoLatestCompletedRun
}
if (-not $runFile) { throw 'DAILY_REPORT_BLOCKED: no completed immutable run with DATA_QUALITY.json exists.' }
$runRoot = $runFile.Directory.FullName
$qualityPath = Join-Path $runRoot 'quality\DATA_QUALITY.json'
if (-not (Test-Path -LiteralPath $qualityPath -PathType Leaf)) { throw 'DAILY_REPORT_BLOCKED: DATA_QUALITY.json is required.' }
$run = Get-Content -LiteralPath $runFile.FullName -Raw | ConvertFrom-Json
$python = Join-Path $repository 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = Join-Path $repository '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $python = $pythonCommand.Source
}
if (-not $WhatIfPreference -and -not (Test-MsoXnysSession -Python $python -TradingDate ([string]$run.trading_date))) {
    throw 'DAILY_REPORT_BLOCKED: source run date is not an XNYS session.'
}
$destination = if ($OutputDirectory) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    Join-Path $runtimeRoot "analysis\$($run.experiment_lane)\$($run.trading_date)\$($run.run_id)"
}

Write-Output 'TASK_NAME=MSO-Daily-Report'
Write-Output "RUN_ID=$($run.run_id)"
Write-Output "SOURCE_RUN=$runRoot"
Write-Output "OUTPUT_DIRECTORY=$destination"
Write-Output "EXECUTION_MODE=$Mode"
Write-Output 'CREDENTIALS_REQUIRED=false'
Write-Output 'NETWORK_REQUIRED=false'
Write-Output 'PAPER_POSITIONS=0'
Write-Output 'REAL_ORDERS=0'

if ($WhatIfPreference) {
    Write-Output 'WHATIF=true'
    Write-Output 'SIDECAR_WRITTEN=false'
    Write-Output 'ORIGINAL_RUN_MUTATED=false'
    exit 0
}
if (-not $PSCmdlet.ShouldProcess($destination, 'Build private read-only daily report sidecar')) { exit 0 }

$savedCredentials = @{}
foreach ($name in @('APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'ALPACA_DATA_FEED')) {
    $savedCredentials[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $null, 'Process')
}
try {
    & $python -I -m market_state_observatory.analysis.daily_report --run $runRoot --output $destination --mode $Mode
    if ($LASTEXITCODE -ne 0) { throw "DAILY_REPORT_FAILED: analysis process exited $LASTEXITCODE" }
}
finally {
    foreach ($name in $savedCredentials.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedCredentials[$name], 'Process')
    }
}
Write-Output 'SIDECAR_WRITTEN=true'
Write-Output 'ORIGINAL_RUN_MUTATED=false'
Write-Output 'PUBLIC_PUSH=false'
