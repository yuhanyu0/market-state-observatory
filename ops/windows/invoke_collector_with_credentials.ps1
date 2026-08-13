[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string[]]$CollectorArguments,
    [switch]$NoLog
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
$credentialPath = Join-Path $runtimeRoot 'secrets\alpaca.credential.xml'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'Runtime configuration is missing.' }
if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) { throw 'Alpaca DPAPI credential is missing.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$runtime = Resolve-MsoRuntimePython -Config $config -RuntimeRoot $runtimeRoot
$credential = Import-Clixml -LiteralPath $credentialPath
$plainKeyId = $credential.UserName
$plainSecret = $credential.GetNetworkCredential().Password
try {
    $environment = @{
        APCA_API_KEY_ID = $plainKeyId
        APCA_API_SECRET_KEY = $plainSecret
        ALPACA_DATA_FEED = 'sip'
        MSO_RUNTIME_ROOT = $runtimeRoot
        MSO_RELEASE_ROOT = $runtime.ReleaseRoot
    }
    $arguments = @('-I') + $CollectorArguments
    $result = Invoke-MsoChildProcess -FileName $runtime.Python -WorkingDirectory $runtime.ReleaseRoot `
        -ArgumentList $arguments -ChildEnvironment $environment `
        -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
    Assert-MsoCredentialSafeOutput -Stdout $result.Stdout -Stderr $result.Stderr `
        -KeyId $plainKeyId -Secret $plainSecret
    if (-not $NoLog) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $logPath = Join-Path $runtimeRoot "logs\collector-$stamp.log"
        @($result.Stdout, $result.Stderr) | Set-Content -LiteralPath $logPath -Encoding UTF8
    }
    Write-Output "MSO_CHILD_PYTHON=$($runtime.Python)"
    Write-Output "MSO_MODULE_PATH=$($runtime.ModulePath)"
    if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
    if ($result.Stderr) { Write-Error $result.Stderr.TrimEnd() -ErrorAction Continue }
    exit $result.ExitCode
}
finally {
    $credential = $null
    $plainKeyId = $null
    $plainSecret = $null
    [GC]::Collect()
}
