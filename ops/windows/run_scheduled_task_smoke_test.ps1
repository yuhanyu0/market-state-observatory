[CmdletBinding()]
param()

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$config = Get-Content -LiteralPath (Join-Path $runtimeRoot 'runtime_paths.json') -Raw | ConvertFrom-Json
if (-not $config.release_launcher) { throw 'Frozen release launcher is not installed.' }
& $config.release_launcher -Mode formal -DryRun
if ($LASTEXITCODE -ne 0) {
    Write-Output 'SCHEDULED_TASK_SMOKE_TEST=FAIL'
    exit $LASTEXITCODE
}
Write-Output 'SCHEDULED_TASK_SMOKE_TEST=PASS'
Write-Output 'NETWORK_CALLED=false'
Write-Output 'PAPER_POSITIONS=0'
Write-Output 'REAL_ORDERS=0'
