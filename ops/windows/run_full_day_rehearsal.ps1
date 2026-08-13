[CmdletBinding()]
param([switch]$DryRun)

& (Join-Path $PSScriptRoot 'run_daily_runtime.ps1') -Mode rehearsal -DryRun:$DryRun
exit $LASTEXITCODE
