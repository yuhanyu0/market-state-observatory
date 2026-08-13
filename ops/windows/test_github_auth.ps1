[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
$ghPath = if ($ghCommand) { $ghCommand.Source } else { Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe' }
if (-not (Test-Path -LiteralPath $ghPath -PathType Leaf)) {
    Write-Output 'GITHUB_CLI=ABSENT'
    exit 1
}
& $ghPath auth status
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$helper = (& git config --global credential.helper) -join ','
if ($helper -match '(^|,)store($|,)') {
    Write-Output 'GITHUB_AUTH=BLOCKED_PLAINTEXT_CREDENTIAL_HELPER'
    exit 1
}
Write-Output 'GITHUB_AUTH=READY'
Write-Output 'TOKEN_DISPLAYED=false'
