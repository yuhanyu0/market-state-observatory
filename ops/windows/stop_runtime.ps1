[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet('MSO-Daily-Rehearsal', 'MSO-Daily-Formal')]
    [string]$TaskName = 'MSO-Daily-Rehearsal',
    [ValidateRange(1, 60)][int]$WaitSeconds = 10,
    [int]$LegacyRuntimePid
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'Runtime is not initialized.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$controlActionId = [Guid]::NewGuid().ToString('N')
$liveRecords = @(Get-MsoLiveOwnedProcesses -RuntimeRoot $runtimeRoot)
$tracked = @{}
foreach ($record in $liveRecords) {
    $recordTask = Get-MsoOptionalPropertyValue -Record $record -Name 'scheduler_task_name'
    if (-not $recordTask -or [string]$recordTask -ne $TaskName) {
        throw "SAFE_STOP_FAIL: live ownership task identity mismatch expected=$TaskName actual=$recordTask."
    }
    $releaseRoot = Get-MsoOptionalPropertyValue -Record $record -Name 'release_root'
    $releasePython = Get-MsoOptionalPropertyValue -Record $record -Name 'release_python'
    if (-not $releaseRoot -or -not $releasePython) {
        throw 'SAFE_STOP_FAIL: live ownership release identity is incomplete.'
    }
    $normalizedRoot = [IO.Path]::GetFullPath([string]$releaseRoot).TrimEnd([char]92)
    $normalizedPython = [IO.Path]::GetFullPath([string]$releasePython)
    if (-not $normalizedPython.StartsWith(
        $normalizedRoot + [char]92,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw 'SAFE_STOP_FAIL: live ownership release path identity is invalid.'
    }
    if (Test-MsoProcessIdentity -Record $record -AllowLauncher) {
        $launcherProcess = Get-MsoProcessById -ProcessId ([int]$record.launcher_pid)
        $tracked[[int]$record.launcher_pid] = Get-MsoProcessCreatedAtUtc -Process $launcherProcess
    }
    $rootPid = if ($record.job_root_pid) { [int]$record.job_root_pid } else { [int]$record.runtime_pid }
    foreach ($process in @(Get-MsoProcessTree -RootPid $rootPid)) {
        $tracked[[int]$process.ProcessId] = Get-MsoProcessCreatedAtUtc -Process $process
    }
}

if ($PSBoundParameters.ContainsKey('LegacyRuntimePid')) {
    $legacy = Get-MsoProcessById -ProcessId $LegacyRuntimePid
    if (-not $legacy) { throw "Legacy runtime PID is not alive: $LegacyRuntimePid" }
    $releasePython = [IO.Path]::GetFullPath([string]$config.release_python)
    $commandLine = [string]$legacy.CommandLine
    $identityMatch = $commandLine.StartsWith('"' + $releasePython + '"', [StringComparison]::OrdinalIgnoreCase) -and
        $commandLine -match 'market_state_observatory\.runtime\.daily_daemon'
    if (-not $identityMatch) { throw 'Legacy runtime identity verification failed; no process was stopped.' }
    foreach ($process in @(Get-MsoProcessTree -RootPid $LegacyRuntimePid)) {
        $tracked[[int]$process.ProcessId] = Get-MsoProcessCreatedAtUtc -Process $process
    }
}

Write-Output "CONTROL_ACTION_ID=$controlActionId"
Write-Output "TASK_NAME=$TaskName"
Write-Output "OWNED_RUNTIME_COUNT=$($liveRecords.Count)"
Write-Output "TRACKED_PIDS=$((@($tracked.Keys | Sort-Object) -join ','))"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task -and [string]$task.State -eq 'Running') {
    if ($PSCmdlet.ShouldProcess($TaskName, 'Stop scheduled task and its owned runtime job')) {
        Stop-ScheduledTask -TaskName $TaskName
        Write-Output 'SCHEDULED_TASK_ACTION=STOP_REQUESTED'
    }
} else {
    Write-Output "SCHEDULED_TASK_ACTION=NO_RUNNING_ACTION state=$(if($task){$task.State}else{'ABSENT'})"
}

$deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
do {
    $remaining = @($tracked.Keys | Where-Object {
        $process = Get-MsoProcessById -ProcessId ([int]$_)
        if (-not $process) { return $false }
        $created = Get-MsoProcessCreatedAtUtc -Process $process
        return $created -eq $tracked[[int]$_]
    })
    if ($remaining.Count -eq 0) { break }
    Start-Sleep -Milliseconds 200
} while ([DateTime]::UtcNow -lt $deadline)

if ($remaining.Count -gt 0) {
    foreach ($record in $liveRecords) {
        $terminated = Stop-MsoNamedJob -JobName ([string]$record.job_object_name)
        Write-Output "JOB_TERMINATE name=$($record.job_object_name) requested=$terminated"
    }
    if ($PSBoundParameters.ContainsKey('LegacyRuntimePid')) {
        $legacyTree = @(Get-MsoProcessTree -RootPid $LegacyRuntimePid | Sort-Object {
            ([string]$_.CommandLine).Length
        } -Descending)
        foreach ($process in $legacyTree) {
            if ($tracked.ContainsKey([int]$process.ProcessId) -and
                (Get-MsoProcessCreatedAtUtc -Process $process) -eq $tracked[[int]$process.ProcessId]) {
                Stop-Process -Id ([int]$process.ProcessId) -Force
                Write-Output "LEGACY_OWNED_PID_TERMINATED=$($process.ProcessId)"
            }
        }
    }
    Start-Sleep -Seconds 2
    foreach ($record in $liveRecords) {
        if (Test-MsoProcessIdentity -Record $record -AllowLauncher) {
            Stop-Process -Id ([int]$record.launcher_pid) -Force
            Write-Output "OWNED_LAUNCHER_TERMINATED=$($record.launcher_pid)"
        }
    }
    Start-Sleep -Milliseconds 500
}

$orphans = @($tracked.Keys | Where-Object {
    $process = Get-MsoProcessById -ProcessId ([int]$_)
    $process -and (Get-MsoProcessCreatedAtUtc -Process $process) -eq $tracked[[int]$_]
})
if ($orphans.Count -gt 0) {
    throw "SAFE_STOP_FAIL: owned process IDs remain=$($orphans -join ',')."
}
foreach ($record in $liveRecords) {
    Set-MsoOwnershipExit -Path $record.ownership_path -Status 'STOPPED_BY_OPERATOR' -ExitCode $null
}

$runtimeStatusPath = Join-Path $runtimeRoot 'operator\runtime_status.json'
$runtimeStatus = if (Test-Path -LiteralPath $runtimeStatusPath -PathType Leaf) {
    try { Get-Content -LiteralPath $runtimeStatusPath -Raw | ConvertFrom-Json } catch { $null }
} else { $null }
$runId = if ($runtimeStatus) { [string]$runtimeStatus.run_id } else { $null }
$runPath = Get-MsoLatestRunPath -RuntimeRoot $runtimeRoot -RunId $runId
$markerPath = $null
$runtimeStatusValue = if ($runtimeStatus) {
    Get-MsoOptionalPropertyValue -Record $runtimeStatus -Name 'runtime_status'
} else { $null }
$hadRuntimeActivity = $liveRecords.Count -gt 0 -or
    $PSBoundParameters.ContainsKey('LegacyRuntimePid') -or
    ($task -and [string]$task.State -eq 'Running') -or
    [string]$runtimeStatusValue -in @('RUNNING', 'STARTING')
if ($hadRuntimeActivity -and $runPath -and
    -not (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $runPath) 'quality\DATA_QUALITY.json'))) {
    $markerPath = New-MsoAbortedRunMarker -RunPath $runPath `
        -Reason 'Scheduler action stopped or runtime process ended before completion.' `
        -ControlActionId $controlActionId
    Write-Output "ABORT_MARKER=$markerPath"
}

$lock = Get-MsoRuntimeLockState -RuntimeRoot $runtimeRoot
if ($lock.State -ne 'ABSENT') {
    if ($lock.State -eq 'ACTIVE_VERIFIED') {
        throw 'SAFE_STOP_FAIL: verified runtime lock owner remains alive.'
    }
    $archive = Join-Path $runtimeRoot "operator\control-events\stale-lock-$controlActionId.json"
    [ordered]@{
        schema_version = 'mso-runtime-control-event-v1'
        control_action_id = $controlActionId
        event = 'STALE_RUNTIME_LOCK_REMOVED_AFTER_PROCESS_VERIFICATION'
        prior_lock_state = $lock.State
        prior_lock_sha256 = (Get-FileHash -LiteralPath $lock.Path -Algorithm SHA256).Hash.ToLowerInvariant()
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        paper_positions = 0
        real_orders = 0
    } | ForEach-Object { Write-MsoAtomicJson -Path $archive -Value $_ }
    Remove-Item -LiteralPath $lock.Path -Force
    Write-Output "STALE_LOCK_ACTION=ARCHIVED_AND_REMOVED state=$($lock.State)"
}
Set-MsoOperatorStoppedStatus -RuntimeRoot $runtimeRoot -RunId $runId `
    -Status 'ABORTED' -Reason 'Operator lifecycle stop completed; immutable run evidence preserved.'

Write-Output 'SAFE_STOP=PASS'
Write-Output 'ORPHAN_COUNT=0'
Write-Output 'UNRELATED_PYTHON_KILLED=0'
Write-Output 'PAPER_POSITIONS=0'
Write-Output 'REAL_ORDERS=0'
