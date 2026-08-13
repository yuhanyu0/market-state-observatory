[CmdletBinding()]
param(
    [ValidateSet('rehearsal', 'formal')][string]$Mode = 'rehearsal',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw 'Runtime is not initialized.'
}
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if (-not $config.release_launcher -or -not (Test-Path -LiteralPath $config.release_launcher -PathType Leaf)) {
    throw 'Formal runtime is fail-closed until an installed frozen release launcher is available.'
}
& $config.release_launcher -Mode $Mode -DryRun:$DryRun
exit $LASTEXITCODE
