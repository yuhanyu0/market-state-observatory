[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)][string]$ReleaseRoot,
    [switch]$Select
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$releaseParent = [IO.Path]::GetFullPath((Join-Path $runtimeRoot 'releases')).TrimEnd([char]92)
$resolvedRelease = [IO.Path]::GetFullPath($ReleaseRoot).TrimEnd([char]92)
if (-not $resolvedRelease.StartsWith($releaseParent + [char]92, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Release selection is restricted to the private runtime releases directory.'
}
$manifestPath = Join-Path $resolvedRelease 'release_manifest.json'
$pythonPath = Join-Path $resolvedRelease 'venv\Scripts\python.exe'
$launcherPath = Join-Path $resolvedRelease 'runtime_release_launcher.ps1'
foreach ($path in @($manifestPath, $pythonPath, $launcherPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Frozen release selection artifact is missing: $path"
    }
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$baseProperty = $manifest.PSObject.Properties['base_python_path']
$probePython = if ($baseProperty -and $baseProperty.Value) { [string]$baseProperty.Value } else { $pythonPath }
$probeEnvironment = @{
    MSO_RUNTIME_ROOT = $runtimeRoot
    MSO_RELEASE_ROOT = $resolvedRelease
}
if (-not $probePython.Equals($pythonPath, [StringComparison]::OrdinalIgnoreCase)) {
    $probeEnvironment.__PYVENV_LAUNCHER__ = $pythonPath
}
$probe = Invoke-MsoChildProcess -FileName $probePython -WorkingDirectory $resolvedRelease `
    -ArgumentList @('-I', '-m', 'market_state_observatory.runtime.release_identity', '--verify-release') `
    -ChildEnvironment $probeEnvironment `
    -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
if ($probe.ExitCode -ne 0 -or $probe.Stdout -notmatch 'RELEASE_INTEGRITY=PASS') {
    throw 'Frozen release selection failed integrity verification.'
}

Write-Output "RELEASE_VERSION=$($manifest.release_version)"
Write-Output "RELEASE_ROOT=$resolvedRelease"
Write-Output "EXPERIMENT_LANE=$($manifest.experiment_lane)"
if (-not $Select -and -not $WhatIfPreference) {
    Write-Output 'SELECT_REQUESTED=false'
    Write-Output 'RUNTIME_CONFIG_CHANGED=false'
    exit 0
}
if ($WhatIfPreference) {
    Write-Output 'SELECT_PREVIEW_ONLY=true'
    Write-Output 'RUNTIME_CONFIG_CHANGED=false'
    exit 0
}
if ($PSCmdlet.ShouldProcess($resolvedRelease, 'Select frozen runtime release')) {
    $configPath = Join-Path $runtimeRoot 'runtime_paths.json'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw 'Runtime is not initialized.'
    }
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    Assert-MsoReleaseSelectionSafe -RuntimeRoot $runtimeRoot
    $config | Add-Member -Force NoteProperty release_root $resolvedRelease
    $config | Add-Member -Force NoteProperty release_python $pythonPath
    $config | Add-Member -Force NoteProperty release_base_python $manifest.base_python_path
    $config | Add-Member -Force NoteProperty release_launcher $launcherPath
    $config | Add-Member -Force NoteProperty release_version $manifest.release_version
    $config | Add-Member -Force NoteProperty release_experiment_lane $manifest.experiment_lane
    $temporary = "$configPath.tmp"
    $config | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $configPath -Force
    Write-Output 'RUNTIME_CONFIG_CHANGED=true'
    Write-Output 'SCHEDULER_CHANGED=false'
}
