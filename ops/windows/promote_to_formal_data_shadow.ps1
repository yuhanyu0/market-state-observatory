[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw 'Runtime is not initialized.'
}
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$runtime = Resolve-MsoRuntimePython -Config $config -RuntimeRoot $runtimeRoot
$result = Invoke-MsoChildProcess -FileName $runtime.Python -WorkingDirectory $runtime.ReleaseRoot `
    -ArgumentList @(
        '-I', '-m', 'market_state_observatory.runtime.formal_promotion',
        '--promote', '--runtime-root', $runtimeRoot
    ) `
    -ChildEnvironment @{
        MSO_RUNTIME_ROOT = $runtimeRoot
        MSO_RELEASE_ROOT = $runtime.ReleaseRoot
    } `
    -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
if ($result.Stderr) { Write-Error $result.Stderr.TrimEnd() -ErrorAction Continue }
exit $result.ExitCode
