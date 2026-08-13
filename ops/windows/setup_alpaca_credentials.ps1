[CmdletBinding()]
param([string]$PythonExecutable)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$credentialPath = Join-Path $runtimeRoot 'secrets\alpaca.credential.xml'
if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot 'runtime_paths.json'))) {
    & (Join-Path $PSScriptRoot 'initialize_runtime.ps1') -PythonExecutable $PythonExecutable
}

$keyId = Read-Host 'Alpaca Key ID'
if ([string]::IsNullOrWhiteSpace($keyId)) { throw 'Key ID cannot be empty.' }
$secret = Read-Host 'Alpaca Secret Key' -AsSecureString
$credential = [System.Management.Automation.PSCredential]::new($keyId, $secret)
if ($credential.GetNetworkCredential().Password.Length -eq 0) { throw 'Secret cannot be empty.' }
$credential | Export-Clixml -LiteralPath $credentialPath -Force
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $credentialPath '/inheritance:r' "/grant:r" "${identity}:F" | Out-Null

$keyId = $null
$secret = $null
$credential = $null
[GC]::Collect()
Write-Output "CREDENTIAL_PATH=$credentialPath"
Write-Output 'CREDENTIAL_SECURITY=DPAPI_CURRENT_WINDOWS_USER_ONLY'
Write-Output 'KEY_ID=PRESENT'
Write-Output 'SECRET=PRESENT'
