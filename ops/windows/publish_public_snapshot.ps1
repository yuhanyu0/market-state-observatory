[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PrivateQualityPath,
    [switch]$Push
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Runtime configuration is missing.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $PrivateQualityPath -PathType Leaf)) { throw 'Private quality file not found.' }
if ($PrivateQualityPath -notlike "$runtimeRoot*") { throw 'Publication input must originate in the private runtime.' }
$arguments = @('scripts/publish_private_snapshot.py', $PrivateQualityPath)
if ($Push) { $arguments += '--push' }
& $config.python_executable @arguments
exit $LASTEXITCODE
