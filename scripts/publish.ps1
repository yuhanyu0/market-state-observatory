[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$PrivateQualityPath, [switch]$Push)
& (Join-Path $PSScriptRoot '..\ops\windows\publish_public_snapshot.ps1') -PrivateQualityPath $PrivateQualityPath -Push:$Push
exit $LASTEXITCODE
