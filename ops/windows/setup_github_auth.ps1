[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI is not installed or not on PATH.'
}
& gh auth status
if ($LASTEXITCODE -ne 0) {
    & gh auth login --web --git-protocol https
    if ($LASTEXITCODE -ne 0) { throw 'GitHub web authentication failed.' }
}
& gh auth setup-git
if ($LASTEXITCODE -ne 0) { throw 'GitHub Git credential integration failed.' }
& gh auth status
if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication verification failed.' }
$helper = (& git config --global credential.helper) -join ','
if ($helper -match '(^|,)store($|,)') {
    throw 'Plaintext Git credential storage detected; automated publication is blocked.'
}
Write-Output 'GITHUB_AUTH=READY'
Write-Output 'TOKEN_DISPLAYED=false'
