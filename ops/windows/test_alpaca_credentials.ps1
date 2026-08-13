[CmdletBinding()]
param()

$invoke = Join-Path $PSScriptRoot 'invoke_collector_with_credentials.ps1'
& $invoke -CollectorArguments @('-m', 'market_state_observatory.runtime.credential_smoke_test') -NoLog
exit $LASTEXITCODE
