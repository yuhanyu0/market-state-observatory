[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$required = @('secrets', 'raw', 'observations', 'data_shadow', 'model_shadow', 'logs', 'locks', 'public_staging', 'backups')
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $runtimeRoot $_) -PathType Container) })
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
$credentialPath = Join-Path $runtimeRoot 'secrets\alpaca.credential.xml'
$status = [ordered]@{
    runtime_path = $runtimeRoot
    runtime_initialized = (Test-Path -LiteralPath $configPath -PathType Leaf)
    missing_directories = $missing
    alpaca_credential = if (Test-Path -LiteralPath $credentialPath) { 'PRESENT' } else { 'ABSENT' }
    private_runtime_inside_repository = $false
    paper_positions = 0
    real_orders = 0
}
$status | ConvertTo-Json -Depth 4
if ($missing.Count -gt 0 -or -not $status.runtime_initialized) { exit 1 }
