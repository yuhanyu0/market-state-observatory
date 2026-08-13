[CmdletBinding()]
param(
    [ValidateSet('rehearsal', 'formal')][string]$Mode = 'formal',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Runtime is not initialized.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$releaseLauncher = $config.release_launcher
if ($Mode -eq 'formal') {
    if (-not $releaseLauncher -or -not (Test-Path -LiteralPath $releaseLauncher -PathType Leaf)) {
        throw 'Formal runtime is fail-closed until a frozen release launcher is installed.'
    }
    & $releaseLauncher -Mode formal -DryRun:$DryRun
    exit $LASTEXITCODE
}
$arguments = @('-m', 'market_state_observatory.runtime.daily_daemon', '--mode', $Mode)
if ($DryRun) {
    $env:MSO_RUNTIME_ROOT = $runtimeRoot
    try {
        & $config.python_executable @arguments '--dry-run'
        exit $LASTEXITCODE
    }
    finally { Remove-Item Env:MSO_RUNTIME_ROOT -ErrorAction SilentlyContinue }
}

$invoke = Join-Path $PSScriptRoot 'invoke_collector_with_credentials.ps1'
& $invoke -CollectorArguments $arguments
$exitCode = $LASTEXITCODE
$failureStage = 'collector'
if ($exitCode -ne 0) {
    $alert = [ordered]@{
        status = 'RUNTIME_HEALTH_ALERT'
        exit_code = $exitCode
        failure_stage = $failureStage
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        credential_values_logged = $false
        paper_positions = 0
        real_orders = 0
    }
    $alertPath = Join-Path $runtimeRoot "logs\health-alert-$([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')).json"
    $alert | ConvertTo-Json | Set-Content -LiteralPath $alertPath -Encoding UTF8
}
exit $exitCode
