[CmdletBinding()]
param([int]$Port = 8765)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'Runtime is not initialized.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if (-not $config.release_python -or -not $config.release_root) { throw 'Frozen runtime release is not installed.' }
$env:MSO_RUNTIME_ROOT = $runtimeRoot
$env:MSO_RELEASE_ROOT = $config.release_root
try {
    & $config.release_python -m market_state_observatory.runtime.operator_console --host 127.0.0.1 --port $Port
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:MSO_RUNTIME_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:MSO_RELEASE_ROOT -ErrorAction SilentlyContinue
}
