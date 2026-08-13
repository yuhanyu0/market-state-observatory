[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
$ghPath = if ($ghCommand) { $ghCommand.Source } else { Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe' }
if (-not (Test-Path -LiteralPath $ghPath -PathType Leaf)) {
    throw 'GitHub CLI is not installed or not on PATH.'
}
& $ghPath auth status
if ($LASTEXITCODE -ne 0) {
    & $ghPath auth login --web --git-protocol https
    if ($LASTEXITCODE -ne 0) { throw 'GitHub web authentication failed.' }
}
& $ghPath auth setup-git
if ($LASTEXITCODE -ne 0) { throw 'GitHub Git credential integration failed.' }
& $ghPath auth status
if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication verification failed.' }
$helper = (& git config --global credential.helper) -join ','
if ($helper -match '(^|,)store($|,)') {
    throw 'Plaintext Git credential storage detected; automated publication is blocked.'
}
Write-Output 'GITHUB_AUTH=READY'
Write-Output 'TOKEN_DISPLAYED=false'
