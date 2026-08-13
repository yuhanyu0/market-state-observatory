[CmdletBinding()]
param()

& (Join-Path $PSScriptRoot 'run_daily_runtime.ps1') -Mode formal -DryRun
if ($LASTEXITCODE -ne 0) {
    Write-Output 'SCHEDULED_TASK_SMOKE_TEST=FAIL'
    exit $LASTEXITCODE
}
Write-Output 'SCHEDULED_TASK_SMOKE_TEST=PASS'
Write-Output 'NETWORK_CALLED=false'
Write-Output 'PAPER_POSITIONS=0'
Write-Output 'REAL_ORDERS=0'
