[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Output 'GITHUB_CLI=ABSENT'
    exit 1
}
& gh auth status
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$helper = (& git config --global credential.helper) -join ','
if ($helper -match '(^|,)store($|,)') {
    Write-Output 'GITHUB_AUTH=BLOCKED_PLAINTEXT_CREDENTIAL_HELPER'
    exit 1
}
Write-Output 'GITHUB_AUTH=READY'
Write-Output 'TOKEN_DISPLAYED=false'
