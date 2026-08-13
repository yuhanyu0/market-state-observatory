[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$required = @(
    'secrets', 'raw', 'observations', 'data_shadow', 'model_shadow', 'logs', 'locks',
    'public_staging', 'backups', 'label_ledger', 'alerts', 'releases', 'operator'
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $runtimeRoot $_) -PathType Container) })
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
$credentialPath = Join-Path $runtimeRoot 'secrets\alpaca.credential.xml'
$config = if (Test-Path -LiteralPath $configPath) { Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } else { $null }
$task = Get-ScheduledTask -TaskName 'MSO-Daily-Runtime' -ErrorAction SilentlyContinue
$publicStatusPath = if ($config) { Join-Path $config.repository_root 'public\data\status.json' } else { $null }
$publicEvidenceAgeHours = $null
if ($publicStatusPath -and (Test-Path -LiteralPath $publicStatusPath)) {
    $publicStatus = Get-Content -LiteralPath $publicStatusPath -Raw | ConvertFrom-Json
    $publicEvidenceAgeHours = ([DateTime]::UtcNow - [DateTime]::Parse($publicStatus.last_evidence_at).ToUniversalTime()).TotalHours
}
$status = [ordered]@{
    runtime_path = $runtimeRoot
    runtime_initialized = (Test-Path -LiteralPath $configPath -PathType Leaf)
    missing_directories = $missing
    alpaca_credential = if (Test-Path -LiteralPath $credentialPath) { 'PRESENT' } else { 'ABSENT' }
    scheduled_task = if ($task) { $task.State.ToString() } else { 'NOT_INSTALLED' }
    public_evidence_age_hours = $publicEvidenceAgeHours
    private_runtime_inside_repository = $false
    paper_positions = 0
    real_orders = 0
}
$status | ConvertTo-Json -Depth 4
if ($config -and $config.release_python) {
    if (-not $task) {
        & $config.release_python -m market_state_observatory.runtime.notifications --kind task_not_started `
            --title 'MSO task not installed' --message 'The daily runtime task is not installed.' 2>$null | Out-Null
    }
    if ($publicEvidenceAgeHours -ne $null -and $publicEvidenceAgeHours -gt 24) {
        & $config.release_python -m market_state_observatory.runtime.notifications --kind public_site_stale `
            --title 'MSO public site stale' --message 'Public evidence is older than 24 hours.' 2>$null | Out-Null
    }
}
if ($missing.Count -gt 0 -or -not $status.runtime_initialized -or -not $task) { exit 1 }
