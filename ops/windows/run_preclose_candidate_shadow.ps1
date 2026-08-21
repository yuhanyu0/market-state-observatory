[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$RunDirectory,
    [int]$DecisionWaitSeconds = 45
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$sourceRootCandidate = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$releaseRoot = if (Test-Path -LiteralPath (Join-Path $sourceRootCandidate 'pyproject.toml') -PathType Leaf) {
    $sourceRootCandidate
} else {
    $PSScriptRoot
}
$processHelper = Join-Path $PSScriptRoot 'lib\process_compat.ps1'
if (-not (Test-Path -LiteralPath $processHelper -PathType Leaf)) {
    $processHelper = Join-Path $releaseRoot 'lib\process_compat.ps1'
}
if (-not $WhatIfPreference) { . $processHelper }

function Get-MsoCurrentCandidateRun {
    $today = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
        [DateTime]::UtcNow, 'Eastern Standard Time'
    ).ToString('yyyy-MM-dd')
    $roots = @(
        (Join-Path $runtimeRoot 'observations'),
        (Join-Path $runtimeRoot 'data_shadow')
    )
    $candidates = @()
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        $candidates += Get-ChildItem -LiteralPath $root -Filter RUN.json -File -Recurse |
            Where-Object {
                $_.Directory.Parent.Name -eq $today -or
                (Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json).trading_date -eq $today
            }
    }
    return $candidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
}

$candidateRoot = Join-Path $runtimeRoot 'prospective_candidate_shadow'
Write-Output 'TASK_NAME=MSO-Preclose-Candidate-Shadow'
Write-Output 'EXECUTION_MODE=PROSPECTIVE_CANDIDATE_SHADOW'
Write-Output 'SCHEDULE=15:46 America/New_York on XNYS sessions'
Write-Output 'DECISION_SOURCE=immutable 15:45 decision_snapshot'
Write-Output 'EXECUTION_QUOTE=15:47 Alpaca SIP data endpoint only'
Write-Output 'BROKER_CLIENT=false'
Write-Output 'ORDER_OBJECT=false'
Write-Output 'PAPER_POSITIONS=0'
Write-Output 'REAL_ORDERS=0'

if ($WhatIfPreference) {
    Write-Output "CANDIDATE_ROOT=$candidateRoot"
    Write-Output 'WHATIF=true'
    Write-Output 'CANDIDATE_WRITTEN=false'
    Write-Output 'NETWORK_CALLED=false'
    Write-Output 'SCHEDULER_CHANGED=false'
    exit 0
}

$runFile = if ($RunDirectory) {
    Get-Item -LiteralPath (Join-Path $RunDirectory 'RUN.json') -ErrorAction Stop
} else {
    Get-MsoCurrentCandidateRun
}
if (-not $runFile) { throw 'PRECLOSE_CANDIDATE_BLOCKED: no current-day immutable run exists.' }
$runRoot = $runFile.Directory.FullName
$run = Get-Content -LiteralPath $runFile.FullName -Raw | ConvertFrom-Json
$decisionPath = Join-Path $runRoot 'manifests\points\decision_snapshot.json'
$deadline = (Get-Date).AddSeconds($DecisionWaitSeconds)
while (-not (Test-Path -LiteralPath $decisionPath -PathType Leaf)) {
    if ((Get-Date) -ge $deadline) {
        throw 'PRECLOSE_CANDIDATE_BLOCKED: decision_snapshot timeout.'
    }
    Start-Sleep -Seconds 1
}
$python = Join-Path $releaseRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = Join-Path $releaseRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$ledgerRoot = Join-Path $candidateRoot "ledgers\v0.5.1rc1"
$candidateDirectory = Join-Path $candidateRoot "preclose\$($run.trading_date)\$($run.run_id)-preclose"
if (-not $PSCmdlet.ShouldProcess($candidateDirectory, 'Freeze prospective candidate and SIP execution quote')) { exit 0 }

& $python -I -m market_state_observatory.analysis.prospective_candidate freeze `
    --run $runRoot --lane preclose --candidate-root $candidateRoot --ledger-root $ledgerRoot `
    --history-run-root (Join-Path $runtimeRoot 'observations') `
    --history-run-root (Join-Path $runtimeRoot 'data_shadow')
if ($LASTEXITCODE -ne 0) { throw "PRECLOSE_CANDIDATE_BLOCKED: freeze exited $LASTEXITCODE" }

$etNow = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'Eastern Standard Time')
$quoteAt = $etNow.Date.AddHours(15).AddMinutes(47)
if ($etNow -lt $quoteAt) {
    Start-Sleep -Milliseconds ([Math]::Ceiling(($quoteAt - $etNow).TotalMilliseconds))
}
$credentialPath = Join-Path $runtimeRoot 'secrets\alpaca.credential.xml'
if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
    throw 'PRECLOSE_CANDIDATE_BLOCKED: Alpaca DPAPI credential is missing.'
}
$credential = Import-Clixml -LiteralPath $credentialPath
$plainKeyId = $credential.UserName
$plainSecret = $credential.GetNetworkCredential().Password
try {
    $environment = @{
        APCA_API_KEY_ID = $plainKeyId
        APCA_API_SECRET_KEY = $plainSecret
        ALPACA_DATA_FEED = 'sip'
        MSO_RUNTIME_ROOT = $runtimeRoot
        MSO_RELEASE_ROOT = $releaseRoot
    }
    $result = Invoke-MsoChildProcess -FileName $python -WorkingDirectory $releaseRoot `
        -ArgumentList @(
            '-I', '-m', 'market_state_observatory.analysis.prospective_candidate',
            'capture-execution-quote', '--candidate-directory', $candidateDirectory
        ) -ChildEnvironment $environment -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
    Assert-MsoCredentialSafeOutput -Stdout $result.Stdout -Stderr $result.Stderr `
        -KeyId $plainKeyId -Secret $plainSecret
    if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
    if ($result.Stderr) { Write-Error $result.Stderr.TrimEnd() -ErrorAction Continue }
    if ($result.ExitCode -ne 0) {
        throw "PRECLOSE_CANDIDATE_BLOCKED: execution quote exited $($result.ExitCode)"
    }
}
finally {
    $credential = $null
    $plainKeyId = $null
    $plainSecret = $null
    [GC]::Collect()
}
Write-Output 'CANDIDATE_WRITTEN=true'
Write-Output 'PUBLIC_PUSH=false'
Write-Output 'FORMAL_DATA_SHADOW_STARTED=false'
Write-Output 'MODEL_SHADOW_STARTED=false'
