[CmdletBinding()]
param([switch]$DryRun)

& (Join-Path $PSScriptRoot 'run_daily_runtime.ps1') -Mode formal -DryRun:$DryRun
exit $LASTEXITCODE
