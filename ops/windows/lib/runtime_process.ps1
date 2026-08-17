Set-StrictMode -Version 2.0

$script:MsoRuntimeProcessVersion = '0.4.5'

function Write-MsoAtomicJson {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Get-MsoStringSha256 {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-', '').ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Get-MsoOptionalPropertyValue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($Record -is [Collections.IDictionary] -and $Record.Contains($Name)) {
        return $Record[$Name]
    }
    $property = $Record.PSObject.Properties[$Name]
    if ($property) { return $property.Value }
    return $null
}

function Get-MsoProcessById {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Get-MsoProcessCreatedAtUtc {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)]$Process)
    return Get-MsoNativeProcessCreatedAtUtc -ProcessId ([int]$Process.ProcessId)
}

function ConvertTo-MsoUtcDateTime {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)]$Value)
    if ($Value -is [DateTime]) { return ([DateTime]$Value).ToUniversalTime() }
    if ($Value -is [DateTimeOffset]) { return ([DateTimeOffset]$Value).UtcDateTime }
    return ([DateTimeOffset]::Parse([string]$Value)).UtcDateTime
}

function Test-MsoProcessIdentity {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Record,
        [switch]$AllowLauncher
    )
    $pidValue = if ($AllowLauncher) {
        Get-MsoOptionalPropertyValue -Record $Record -Name 'launcher_pid'
    } else {
        Get-MsoOptionalPropertyValue -Record $Record -Name 'runtime_pid'
    }
    if (-not $pidValue) { return $false }
    $process = Get-MsoProcessById -ProcessId ([int]$pidValue)
    if (-not $process) { return $false }
    $expectedCreated = if ($AllowLauncher) {
        Get-MsoOptionalPropertyValue -Record $Record -Name 'launcher_created_at_utc'
    } else {
        Get-MsoOptionalPropertyValue -Record $Record -Name 'runtime_created_at_utc'
    }
    if ($expectedCreated) {
        $actualText = [string](Get-MsoProcessCreatedAtUtc -Process $process)
        $actualUtc = ConvertTo-MsoUtcDateTime -Value $actualText
        $expectedUtc = ConvertTo-MsoUtcDateTime -Value $expectedCreated
        $creationDelta = [Math]::Abs(($actualUtc - $expectedUtc).TotalSeconds)
        Write-Verbose "pid=$pidValue creation_delta_seconds=$creationDelta actual=$actualText expected=$($expectedUtc.ToString('o'))"
        if ($creationDelta -gt 2) { return $false }
    }
    if ($AllowLauncher) {
        $launcherExecutableProperty = $Record.PSObject.Properties['launcher_executable']
        if ($launcherExecutableProperty -and $launcherExecutableProperty.Value) {
            $actualLauncher = [IO.Path]::GetFullPath([string]$process.ExecutablePath)
            $expectedLauncher = [IO.Path]::GetFullPath([string]$launcherExecutableProperty.Value)
            if (-not $actualLauncher.Equals($expectedLauncher, [StringComparison]::OrdinalIgnoreCase)) {
                return $false
            }
        }
        $commandHashProperty = $Record.PSObject.Properties['launcher_command_line_sha256']
        if ($commandHashProperty -and $commandHashProperty.Value -and
            (Get-MsoStringSha256 -Value ([string]$process.CommandLine)) -ne $commandHashProperty.Value) {
            return $false
        }
        return $true
    }
    if (-not $AllowLauncher) {
        $processExecutable = Get-MsoOptionalPropertyValue -Record $Record -Name 'process_executable'
        $releaseBasePython = Get-MsoOptionalPropertyValue -Record $Record -Name 'release_base_python'
        $releasePython = Get-MsoOptionalPropertyValue -Record $Record -Name 'release_python'
        $expectedPythonValue = if ($processExecutable) { $processExecutable } `
            elseif ($releaseBasePython) { $releaseBasePython } `
            else { $releasePython }
        if (-not $expectedPythonValue) { return $false }
        $expectedPython = [IO.Path]::GetFullPath([string]$expectedPythonValue)
        $actualExecutable = if ($process.ExecutablePath) {
            [IO.Path]::GetFullPath([string]$process.ExecutablePath)
        } else { '' }
        $commandLine = [string]$process.CommandLine
        $commandUsesReleasePython = $commandLine.StartsWith(
            '"' + $expectedPython + '"', [StringComparison]::OrdinalIgnoreCase
        ) -or $commandLine.StartsWith(
            $expectedPython + ' ', [StringComparison]::OrdinalIgnoreCase
        )
        $executableMatches = $actualExecutable.Equals($expectedPython, [StringComparison]::OrdinalIgnoreCase)
        Write-Verbose "pid=$pidValue executable_matches=$executableMatches command_matches=$commandUsesReleasePython"
        if (-not $executableMatches -and
            -not $commandUsesReleasePython) {
            return $false
        }
        if ($commandLine -notmatch 'market_state_observatory\.runtime\.daily_daemon|mso_lifecycle_test_child') {
            return $false
        }
    }
    return $true
}

function Get-MsoOwnershipRecords {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RuntimeRoot)
    $directory = Join-Path $RuntimeRoot 'operator\process-ownership'
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { return @() }
    return @(
        Get-ChildItem -LiteralPath $directory -Filter *.json -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                try {
                    $record = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
                    $record | Add-Member -Force NoteProperty ownership_path $_.FullName
                    $record
                } catch { }
            }
    )
}

function Get-MsoLiveOwnedProcesses {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RuntimeRoot)
    return @(
        Get-MsoOwnershipRecords -RuntimeRoot $RuntimeRoot |
            Where-Object {
                $runtimeLive = Test-MsoProcessIdentity -Record $_
                $status = Get-MsoOptionalPropertyValue -Record $_ -Name 'status'
                $activeStatus = [string]$status -in @('STARTING_SUSPENDED', 'RUNNING')
                $launcherLive = $activeStatus -and (Test-MsoProcessIdentity -Record $_ -AllowLauncher)
                $runtimeLive -or $launcherLive
            }
    )
}

function Get-MsoRuntimeLockState {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RuntimeRoot)
    $path = Join-Path $RuntimeRoot 'locks\daily-runtime.lock'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return [pscustomobject]@{ State = 'ABSENT'; Path = $path; Payload = $null; Process = $null }
    }
    try { $payload = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
    catch { return [pscustomobject]@{ State = 'INVALID'; Path = $path; Payload = $null; Process = $null } }
    $process = if ($payload.pid) { Get-MsoProcessById -ProcessId ([int]$payload.pid) } else { $null }
    if (-not $process) {
        return [pscustomobject]@{ State = 'STALE_DEAD_PID'; Path = $path; Payload = $payload; Process = $null }
    }
    $createdProperty = $payload.PSObject.Properties['process_created_at_utc']
    $releaseProperty = $payload.PSObject.Properties['release_python']
    if (-not $createdProperty -or -not $releaseProperty -or
        -not $createdProperty.Value -or -not $releaseProperty.Value) {
        return [pscustomobject]@{ State = 'LEGACY_PID_REUSED_OR_UNVERIFIED'; Path = $path; Payload = $payload; Process = $process }
    }
    $processExecutableProperty = $payload.PSObject.Properties['process_executable']
    $record = [pscustomobject]@{
        runtime_pid = $payload.pid
        runtime_created_at_utc = $createdProperty.Value
        release_python = if ($processExecutableProperty -and $processExecutableProperty.Value) {
            $processExecutableProperty.Value
        } else { $releaseProperty.Value }
    }
    $state = if (Test-MsoProcessIdentity -Record $record) { 'ACTIVE_VERIFIED' } else { 'STALE_PID_REUSED' }
    return [pscustomobject]@{ State = $state; Path = $path; Payload = $payload; Process = $process }
}

function Assert-MsoRuntimeStartSafe {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RuntimeRoot,
        [Parameter(Mandatory = $true)]$Config,
        [Parameter(Mandatory = $true)][ValidateSet('rehearsal', 'formal')][string]$Mode,
        [string]$ScheduledTaskName
    )
    $expectedTask = if ($Mode -eq 'formal') { 'MSO-Daily-Formal' } else { 'MSO-Daily-Rehearsal' }
    if ($ScheduledTaskName -and $ScheduledTaskName -ne $expectedTask) {
        throw 'RUNTIME_START_REJECTED: scheduler mode and task identity do not match.'
    }
    if ($ScheduledTaskName) {
        $task = Get-ScheduledTask -TaskName $ScheduledTaskName -ErrorAction SilentlyContinue
        if (-not $task -or [string]$task.State -eq 'Disabled') {
            throw 'RUNTIME_START_REJECTED: declared scheduler task is absent or disabled.'
        }
        $otherTaskName = if ($Mode -eq 'formal') { 'MSO-Daily-Rehearsal' } else { 'MSO-Daily-Formal' }
        $otherTask = Get-ScheduledTask -TaskName $otherTaskName -ErrorAction SilentlyContinue
        if ($otherTask -and [string]$otherTask.State -ne 'Disabled') {
            throw 'RUNTIME_START_REJECTED: opposite scheduler mode is active.'
        }
    }
    $live = @(Get-MsoLiveOwnedProcesses -RuntimeRoot $RuntimeRoot)
    if ($live.Count -gt 0) {
        throw "RUNTIME_START_REJECTED: live MSO-owned process exists pid=$($live[0].runtime_pid)."
    }
    $lock = Get-MsoRuntimeLockState -RuntimeRoot $RuntimeRoot
    if ($lock.State -ne 'ABSENT') {
        throw "RUNTIME_START_REJECTED: runtime lock is not clean state=$($lock.State). Run stop_runtime.ps1."
    }
}

function Assert-MsoReleaseSelectionSafe {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RuntimeRoot)
    foreach ($taskName in @('MSO-Daily-Rehearsal', 'MSO-Daily-Formal')) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($task -and [string]$task.State -ne 'Disabled') {
            throw "RELEASE_SELECTION_REJECTED: task is active task=$taskName state=$($task.State)."
        }
    }
    $live = @(Get-MsoLiveOwnedProcesses -RuntimeRoot $RuntimeRoot)
    if ($live.Count -gt 0) {
        throw "RELEASE_SELECTION_REJECTED: live MSO-owned process pid=$($live[0].runtime_pid) release=$($live[0].release_version)."
    }
    $lock = Get-MsoRuntimeLockState -RuntimeRoot $RuntimeRoot
    if ($lock.State -eq 'ACTIVE_VERIFIED') {
        throw "RELEASE_SELECTION_REJECTED: active runtime lock pid=$($lock.Payload.pid)."
    }
    if ($lock.State -ne 'ABSENT') {
        throw "RELEASE_SELECTION_REJECTED: unresolved runtime lock state=$($lock.State). Run stop_runtime.ps1."
    }
}

function New-MsoProcessOwnershipRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RuntimeRoot,
        [Parameter(Mandatory = $true)][string]$OwnershipId,
        [Parameter(Mandatory = $true)][int]$RuntimePid,
        [Parameter(Mandatory = $true)][string]$JobName,
        [Parameter(Mandatory = $true)][string]$ReleaseVersion,
        [Parameter(Mandatory = $true)][string]$ReleaseRoot,
        [Parameter(Mandatory = $true)][string]$ReleasePython,
        [string]$ProcessExecutable,
        [Parameter(Mandatory = $true)][string]$Mode,
        [string]$SchedulerTaskName
    )
    $launcher = Get-MsoProcessById -ProcessId $PID
    $runtime = Get-MsoProcessById -ProcessId $RuntimePid
    if (-not $launcher -or -not $runtime) { throw 'Process ownership identity could not be captured.' }
    $path = Join-Path $RuntimeRoot "operator\process-ownership\$OwnershipId.json"
    $record = [ordered]@{
        schema_version = 'mso-runtime-process-ownership-v1'
        ownership_id = $OwnershipId
        status = 'STARTING_SUSPENDED'
        launcher_pid = $PID
        launcher_created_at_utc = Get-MsoProcessCreatedAtUtc -Process $launcher
        launcher_executable = [string]$launcher.ExecutablePath
        launcher_command_line_sha256 = Get-MsoStringSha256 -Value ([string]$launcher.CommandLine)
        runtime_pid = $RuntimePid
        runtime_created_at_utc = Get-MsoProcessCreatedAtUtc -Process $runtime
        job_root_pid = $RuntimePid
        job_root_created_at_utc = Get-MsoProcessCreatedAtUtc -Process $runtime
        job_object_owned = $true
        job_object_name = $JobName
        scheduler_task_name = $SchedulerTaskName
        mode = $Mode
        release_version = $ReleaseVersion
        release_root = $ReleaseRoot
        release_python = $ReleasePython
        process_executable = if ($ProcessExecutable) { $ProcessExecutable } else { $ReleasePython }
        run_id = $null
        created_at_utc = [DateTime]::UtcNow.ToString('o')
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
        paper_positions = 0
        real_orders = 0
    }
    Write-MsoAtomicJson -Path $path -Value $record
    return [pscustomobject]@{ Path = $path; Record = $record }
}

function Get-MsoProcessTree {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][int]$RootPid)
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $pending = New-Object System.Collections.Queue
    $pending.Enqueue($RootPid)
    $seen = @{}
    $result = @()
    while ($pending.Count -gt 0) {
        $parent = [int]$pending.Dequeue()
        if ($seen.ContainsKey($parent)) { continue }
        $seen[$parent] = $true
        $process = $all | Where-Object { [int]$_.ProcessId -eq $parent } | Select-Object -First 1
        if ($process) { $result += $process }
        foreach ($child in @($all | Where-Object { [int]$_.ParentProcessId -eq $parent })) {
            $pending.Enqueue([int]$child.ProcessId)
        }
    }
    return @($result)
}

function Get-MsoLatestRunPath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RuntimeRoot,
        [string]$RunId
    )
    $roots = @(Join-Path $RuntimeRoot 'observations\rehearsals'), @(Join-Path $RuntimeRoot 'data_shadow')
    $candidates = @()
    foreach ($root in $roots) {
        if (Test-Path -LiteralPath $root -PathType Container) {
            $candidates += @(Get-ChildItem -LiteralPath $root -Filter RUN.json -File -Recurse -ErrorAction SilentlyContinue)
        }
    }
    if ($RunId) {
        $match = $candidates | Where-Object {
            try { (Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json).run_id -eq $RunId }
            catch { $false }
        } | Select-Object -First 1
        if ($match) { return $match.FullName }
    }
    $latest = $candidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return $null
}

function New-MsoAbortedRunMarker {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RunPath,
        [Parameter(Mandatory = $true)][string]$Reason,
        [Parameter(Mandatory = $true)][string]$ControlActionId
    )
    $run = Get-Content -LiteralPath $RunPath -Raw | ConvertFrom-Json
    $runDirectory = Split-Path -Parent $RunPath
    $controlDirectory = Join-Path $runDirectory 'control'
    New-Item -ItemType Directory -Path $controlDirectory -Force | Out-Null
    $existing = Get-ChildItem -LiteralPath $controlDirectory -Filter 'ABORTED-*.json' -File `
        -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
    if ($existing) { return $existing.FullName }
    $path = Join-Path $controlDirectory "ABORTED-$ControlActionId.json"
    if (Test-Path -LiteralPath $path) { return $path }
    $recovery = Get-ChildItem -LiteralPath (Join-Path $runDirectory 'recovery') -Filter *.json -File `
        -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    $recoveryPayload = if ($recovery) {
        Get-Content -LiteralPath $recovery.FullName -Raw | ConvertFrom-Json
    } else { $null }
    $qualityExists = Test-Path -LiteralPath (Join-Path $runDirectory 'quality\DATA_QUALITY.json') -PathType Leaf
    $marker = [ordered]@{
        schema_version = 'mso-runtime-abort-control-v1'
        control_action_id = $ControlActionId
        source_run_id = $run.run_id
        source_run_sha256 = (Get-FileHash -LiteralPath $RunPath -Algorithm SHA256).Hash.ToLowerInvariant()
        status = 'ABORTED_INCOMPLETE_CRASHED'
        reason = $Reason
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        immutable_run_rewritten = $false
        backfill_attempted = $false
        data_quality_pass = $false
        quality_artifact_exists = $qualityExists
        completed_observations = [object[]]$(if ($recoveryPayload) { @($recoveryPayload.completed) } else { @() })
        missed_observations = [object[]]$(if ($recoveryPayload) { @($recoveryPayload.missed) } else { @() })
        counts_toward_20_day_gate = $false
        counts_toward_model_shadow = $false
        paper_positions = 0
        real_orders = 0
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($marker | ConvertTo-Json -Depth 8))
    $stream = New-Object IO.FileStream($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    return $path
}

function Set-MsoOperatorStoppedStatus {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RuntimeRoot,
        [string]$RunId,
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Reason
    )
    $path = Join-Path $RuntimeRoot 'operator\runtime_status.json'
    $payload = [ordered]@{
        schema_version = 'mso-private-runtime-heartbeat-v1'
        runtime_status = $Status
        phase = 'STOPPED'
        heartbeat_at_utc = [DateTime]::UtcNow.ToString('o')
        run_id = $RunId
        process_truth = 'NO_LIVE_MSO_RUNTIME'
        stop_reason = $Reason
        counts_toward_20_day_gate = $false
        paper_positions = 0
        real_orders = 0
    }
    Write-MsoAtomicJson -Path $path -Value $payload
}

function Set-MsoOwnershipExit {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Status,
        [AllowNull()][Nullable[int]]$ExitCode
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $record = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $record.status = $Status
    $record | Add-Member -Force NoteProperty exit_code $ExitCode
    $record | Add-Member -Force NoteProperty ended_at_utc ([DateTime]::UtcNow.ToString('o'))
    $record.updated_at_utc = [DateTime]::UtcNow.ToString('o')
    Write-MsoAtomicJson -Path $Path -Value $record
}
