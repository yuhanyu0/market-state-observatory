[CmdletBinding()]
param(
    [ValidateSet('rehearsal', 'formal')][string]$Mode = 'rehearsal',
    [switch]$DryRun,
    [ValidateSet('MSO-Daily-Rehearsal', 'MSO-Daily-Formal')][string]$ScheduledTaskName
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'Runtime is not initialized.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$launcherReleaseRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path.TrimEnd([char]92)
$selectedReleaseRoot = [IO.Path]::GetFullPath([string]$config.release_root).TrimEnd([char]92)
if (-not $launcherReleaseRoot.Equals($selectedReleaseRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Selected runtime release does not match this frozen launcher.'
}
$runtime = Resolve-MsoRuntimePython -Config $config -RuntimeRoot $runtimeRoot
$launcherMutex = New-Object System.Threading.Mutex($false, 'Local\MarketStateObservatoryRuntime-Daily-v1')
$launcherMutexOwned = $false
try {
    $launcherMutexOwned = $launcherMutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
    $launcherMutexOwned = $true
}
if (-not $launcherMutexOwned) {
    throw 'RUNTIME_START_REJECTED: another launcher owns the runtime mutex.'
}
Assert-MsoRuntimeStartSafe -RuntimeRoot $runtimeRoot -Config $config -Mode $Mode `
    -ScheduledTaskName $ScheduledTaskName

function Invoke-ReleasePython {
    param([string[]]$Arguments, [switch]$WithCredential, [switch]$OwnedRuntime)
    $credential = $null
    $plainKeyId = $null
    $plainSecret = $null
    $environment = @{
        MSO_RUNTIME_ROOT = $runtimeRoot
        MSO_RELEASE_ROOT = $runtime.ReleaseRoot
        MSO_SOURCE_ROOT = $config.repository_root
    }
    if ($ScheduledTaskName) { $environment.MSO_SCHEDULER_TASK_NAME = $ScheduledTaskName }
    try {
        if ($WithCredential) {
            $credentialPath = Join-Path $runtimeRoot 'secrets\alpaca.credential.xml'
            if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
                throw 'Alpaca DPAPI credential is missing.'
            }
            $credential = Import-Clixml -LiteralPath $credentialPath
            $plainKeyId = $credential.UserName
            $plainSecret = $credential.GetNetworkCredential().Password
            $environment.APCA_API_KEY_ID = $plainKeyId
            $environment.APCA_API_SECRET_KEY = $plainSecret
            $environment.ALPACA_DATA_FEED = 'sip'
        }
        $isolatedArguments = @('-I') + $Arguments
        if ($OwnedRuntime) {
            $result = Invoke-MsoOwnedChildProcess -FileName $runtime.BasePython `
                -WorkingDirectory $runtime.ReleaseRoot -ArgumentList $isolatedArguments `
                -ChildEnvironment $environment -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME') `
                -RuntimeRoot $runtimeRoot -ReleaseVersion $config.release_version `
                -ReleaseRoot $runtime.ReleaseRoot -ReleasePython $runtime.Python `
                -Mode $Mode -SchedulerTaskName $ScheduledTaskName
        } else {
            $result = Invoke-MsoChildProcess -FileName $runtime.Python `
                -WorkingDirectory $runtime.ReleaseRoot -ArgumentList $isolatedArguments `
                -ChildEnvironment $environment -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
        }
        if ($WithCredential) {
            Assert-MsoCredentialSafeOutput -Stdout $result.Stdout -Stderr $result.Stderr `
                -KeyId $plainKeyId -Secret $plainSecret
        }
        return $result
    }
    finally {
        $credential = $null
        $plainKeyId = $null
        $plainSecret = $null
        [GC]::Collect()
    }
}

function Send-MsoAlert {
    param([string]$Kind, [string]$Title, [string]$Message)
    $alert = Invoke-ReleasePython -Arguments @(
        '-m', 'market_state_observatory.runtime.notifications',
        '--kind', $Kind, '--title', $Title, '--message', $Message
    )
    if ($alert.ExitCode -ne 0) { return }
}

Write-Output $runtime.IntegrityOutput
Write-Output "MSO_CHILD_PYTHON=$($runtime.Python)"
Write-Output "MSO_MODULE_PATH=$($runtime.ModulePath)"
$arguments = @('-m', 'market_state_observatory.runtime.daily_daemon', '--mode', $Mode)
if ($DryRun) { $arguments += '--dry-run' }
try {
    $result = Invoke-ReleasePython -Arguments $arguments -WithCredential:(-not $DryRun) `
        -OwnedRuntime
}
catch {
    $kind = if ($_.Exception.Message -match 'credential') { 'credential_invalid' } else { 'task_not_started' }
    Send-MsoAlert -Kind $kind -Title 'MSO runtime blocked' `
        -Message 'The frozen data runtime did not start. Review the private operator console.'
    throw
}
$stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
$logPath = Join-Path $runtimeRoot "logs\release-runtime-$stamp.log"
@($result.Stdout, $result.Stderr) | Set-Content -LiteralPath $logPath -Encoding UTF8
if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
if ($result.Stderr) { Write-Error $result.Stderr.TrimEnd() -ErrorAction Continue }
if ($result.ExitCode -ne 0) {
    Send-MsoAlert -Kind 'quality_failed' -Title 'MSO runtime failed' `
        -Message 'The runtime exited nonzero. No public state was updated.'
}
if ($result.ExitCode -ne 0 -or $DryRun -or $Mode -ne 'formal') {
    if ($launcherMutexOwned) { $launcherMutex.ReleaseMutex(); $launcherMutexOwned = $false }
    $launcherMutex.Dispose()
    exit $result.ExitCode
}

$etNow = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
    [DateTime]::UtcNow,
    'Eastern Standard Time'
)
$dayRoot = Join-Path $runtimeRoot "data_shadow\$($config.release_experiment_lane)\$($etNow.ToString('yyyy-MM-dd'))"
$quality = Get-ChildItem -LiteralPath $dayRoot -Filter 'DATA_QUALITY.json' -File -Recurse `
    -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $quality) { throw 'Publication blocked: immutable quality artifact is missing.' }
$publish = Invoke-ReleasePython -Arguments @(
    '-m', 'market_state_observatory.publication.runtime_publisher',
    '--repository', $config.repository_root,
    '--quality', $quality.FullName,
    '--push'
)
@($publish.Stdout, $publish.Stderr) | Set-Content -LiteralPath `
    (Join-Path $runtimeRoot "logs\publication-$stamp.log") -Encoding UTF8
if ($publish.Stdout) { Write-Output $publish.Stdout.TrimEnd() }
if ($publish.Stderr) { Write-Error $publish.Stderr.TrimEnd() -ErrorAction Continue }
if ($publish.ExitCode -ne 0) {
    Send-MsoAlert -Kind 'publication_failed' -Title 'MSO publication failed' `
        -Message 'Fail-closed publication rejected or could not publish the run.'
}
if ($launcherMutexOwned) { $launcherMutex.ReleaseMutex(); $launcherMutexOwned = $false }
$launcherMutex.Dispose()
exit $publish.ExitCode
