[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PythonExecutable,
    [ValidateSet('Suite', 'TaskLauncher', 'CrashLauncher')][string]$Mode = 'Suite',
    [string]$TestRoot,
    [string]$TaskName
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $root 'ops\windows\lib\process_compat.ps1')

function Wait-MsoCondition {
    param([scriptblock]$Condition, [int]$Seconds = 20)
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        if (& $Condition) { return $true }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

function Test-PidAlive {
    param([int]$Id)
    return $null -ne (Get-Process -Id $Id -ErrorAction SilentlyContinue)
}

function Get-PidIdentity {
    param([int]$Id)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $Id" -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    return [pscustomobject]@{
        Id = $Id
        Created = Get-MsoNativeProcessCreatedAtUtc -ProcessId $Id
    }
}

function Test-PidIdentityAlive {
    param($Identity)
    if (-not $Identity) { return $false }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($Identity.Id)" -ErrorAction SilentlyContinue
    if (-not $process) { return $false }
    return (Get-MsoNativeProcessCreatedAtUtc -ProcessId $Identity.Id) -eq $Identity.Created
}

function Assert-True {
    param([bool]$Value, [string]$Name)
    if (-not $Value) { throw "$Name failed" }
}

function Invoke-TestLauncher {
    $treePath = Join-Path $TestRoot 'tree.json'
    $launcherPath = Join-Path $TestRoot 'launcher.json'
    [ordered]@{ pid = $PID; created_at_utc = [DateTime]::UtcNow.ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $launcherPath -Encoding UTF8
    $code = @'
# mso_lifecycle_test_child
import json, os, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(300)"])
with open(os.environ["MSO_TEST_TREE_PATH"], "w", encoding="utf-8") as stream:
    json.dump({"runtime_pid": os.getpid(), "child_pid": child.pid}, stream)
    stream.flush()
    os.fsync(stream.fileno())
time.sleep(300)
'@
    $result = Invoke-MsoOwnedChildProcess -FileName $PythonExecutable `
        -WorkingDirectory $TestRoot -ArgumentList @('-I', '-c', $code) `
        -ChildEnvironment @{ MSO_TEST_TREE_PATH = $treePath } `
        -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME') -RuntimeRoot $TestRoot `
        -ReleaseVersion '0.4.5-test' -ReleaseRoot $TestRoot -Mode rehearsal `
        -SchedulerTaskName $TaskName
    if ($result.ExitCode -ne 0) {
        [ordered]@{
            exit_code = $result.ExitCode
            stdout = $result.Stdout
            stderr = $result.Stderr
        } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $TestRoot 'launcher-error.json') -Encoding UTF8
    }
    exit $result.ExitCode
}

if ($Mode -ne 'Suite') { Invoke-TestLauncher }

$PythonExecutable = (Resolve-Path -LiteralPath $PythonExecutable).Path
$PythonExecutable = (& $PythonExecutable -I -c 'import sys; print(sys._base_executable)').Trim()
if (-not $TestRoot) {
    $TestRoot = Join-Path ([IO.Path]::GetTempPath()) "mso-lifecycle-$([Guid]::NewGuid().ToString('N'))"
}
New-Item -ItemType Directory -Path $TestRoot -Force | Out-Null
$testTask = "MSO-Lifecycle-v045-$([Guid]::NewGuid().ToString('N').Substring(0,10))"
$unrelated = $null
$crashLauncher = $null
try {
    $windowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $taskArguments = ConvertTo-WindowsCommandLine @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
        '-File', $PSCommandPath, '-PythonExecutable', $PythonExecutable, '-Mode', 'TaskLauncher',
        '-TestRoot', $TestRoot, '-TaskName', $testTask
    )
    $action = New-ScheduledTaskAction -Execute $windowsPowerShell -Argument $taskArguments `
        -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddHours(1)
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    $principal = New-ScheduledTaskPrincipal `
        -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $testTask -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
    Start-ScheduledTask -TaskName $testTask
    $scheduledStarted = Wait-MsoCondition {
        (Test-Path -LiteralPath (Join-Path $TestRoot 'tree.json')) -or
        (Test-Path -LiteralPath (Join-Path $TestRoot 'launcher-error.json'))
    }
    Assert-True $scheduledStarted 'scheduled child response'
    if (Test-Path -LiteralPath (Join-Path $TestRoot 'launcher-error.json')) {
        $launcherError = Get-Content -LiteralPath (Join-Path $TestRoot 'launcher-error.json') -Raw
        throw "scheduled child start failed: $launcherError"
    }
    $launcher = Get-Content -LiteralPath (Join-Path $TestRoot 'launcher.json') -Raw | ConvertFrom-Json
    $tree = Get-Content -LiteralPath (Join-Path $TestRoot 'tree.json') -Raw | ConvertFrom-Json
    $scheduledPids = @([int]$launcher.pid, [int]$tree.runtime_pid, [int]$tree.child_pid)
    $scheduledIdentities = @($scheduledPids | ForEach-Object { Get-PidIdentity $_ })
    $scheduledOwnership = Get-MsoOwnershipRecords -RuntimeRoot $TestRoot |
        Sort-Object created_at_utc -Descending | Select-Object -First 1
    Assert-True ($null -ne $scheduledOwnership) 'scheduled ownership record'
    $runtimeInJob = Test-MsoProcessInNamedJob -ProcessId ([int]$tree.runtime_pid) `
        -JobName ([string]$scheduledOwnership.job_object_name)
    $childInJob = Test-MsoProcessInNamedJob -ProcessId ([int]$tree.child_pid) `
        -JobName ([string]$scheduledOwnership.job_object_name)
    Write-Output "PRE_STOP_RUNTIME_IN_JOB=$runtimeInJob"
    Write-Output "PRE_STOP_CHILD_IN_JOB=$childInJob"
    Assert-True ($runtimeInJob -and $childInJob) 'entire descendant tree assigned to owned Job'
    Stop-ScheduledTask -TaskName $testTask
    $stopClean = Wait-MsoCondition { @($scheduledIdentities | Where-Object { Test-PidIdentityAlive $_ }).Count -eq 0 }
    if (-not $stopClean) {
        $remainingAfterStop = @($scheduledIdentities | Where-Object { Test-PidIdentityAlive $_ } | ForEach-Object Id)
        $taskAfterStop = Get-ScheduledTask -TaskName $testTask
        Write-Output "STOP_DIAGNOSTIC_REMAINING=$($remainingAfterStop -join ',')"
        Write-Output "STOP_DIAGNOSTIC_LAUNCHER=$($launcher.pid) RUNTIME=$($tree.runtime_pid) CHILD=$($tree.child_pid)"
        foreach ($remainingPid in $remainingAfterStop) {
            Get-CimInstance Win32_Process -Filter "ProcessId = $remainingPid" |
                Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | Format-List
        }
        Write-Output "STOP_DIAGNOSTIC_TASK_STATE=$($taskAfterStop.State)"
    }
    Assert-True $stopClean 'Stop-ScheduledTask descendant cleanup'
    Write-Output "STOP_SCHEDULED_TASK_PIDS=$($scheduledPids -join ',')"
    Write-Output 'STOP_SCHEDULED_TASK_DESCENDANTS=PASS'
    Write-Output 'ORPHAN_COUNT_AFTER_STOP=0'

    Remove-Item -LiteralPath (Join-Path $TestRoot 'tree.json') -Force
    Remove-Item -LiteralPath (Join-Path $TestRoot 'launcher.json') -Force
    Start-ScheduledTask -TaskName $testTask
    Assert-True (Wait-MsoCondition { Test-Path -LiteralPath (Join-Path $TestRoot 'tree.json') }) `
        'disable-truth child start'
    $launcher = Get-Content -LiteralPath (Join-Path $TestRoot 'launcher.json') -Raw | ConvertFrom-Json
    $tree = Get-Content -LiteralPath (Join-Path $TestRoot 'tree.json') -Raw | ConvertFrom-Json
    $disablePids = @([int]$launcher.pid, [int]$tree.runtime_pid, [int]$tree.child_pid)
    $disableIdentities = @($disablePids | ForEach-Object { Get-PidIdentity $_ })
    Disable-ScheduledTask -TaskName $testTask | Out-Null
    Assert-True (Test-PidAlive ([int]$tree.runtime_pid)) 'disabled task process truth remains active'
    Write-Output 'DISABLE_WHILE_ACTIVE_PROCESS_TRUTH=ACTIVE_VERIFIED'
    $activeRecord = Get-MsoOwnershipRecords -RuntimeRoot $TestRoot |
        Sort-Object created_at_utc -Descending | Select-Object -First 1
    Assert-True ($null -ne $activeRecord) 'disable-truth ownership record'
    [void](Stop-MsoNamedJob -JobName ([string]$activeRecord.job_object_name))
    Assert-True (Wait-MsoCondition { @($disableIdentities | Where-Object { Test-PidIdentityAlive $_ }).Count -eq 0 }) `
        'disable-truth controlled cleanup'
    Enable-ScheduledTask -TaskName $testTask | Out-Null

    Remove-Item -LiteralPath (Join-Path $TestRoot 'tree.json') -Force
    Remove-Item -LiteralPath (Join-Path $TestRoot 'launcher.json') -Force
    $crashTaskName = "MSO-Lifecycle-Crash-$([Guid]::NewGuid().ToString('N').Substring(0,10))"
    $crashArguments = ConvertTo-WindowsCommandLine @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath,
        '-PythonExecutable', $PythonExecutable, '-Mode', 'CrashLauncher', '-TestRoot', $TestRoot,
        '-TaskName', $crashTaskName
    )
    $crashLauncher = Start-Process -FilePath $windowsPowerShell -ArgumentList $crashArguments `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru
    Assert-True (Wait-MsoCondition { Test-Path -LiteralPath (Join-Path $TestRoot 'tree.json') }) `
        'crash child start'
    $tree = Get-Content -LiteralPath (Join-Path $TestRoot 'tree.json') -Raw | ConvertFrom-Json
    $crashPids = @([int]$crashLauncher.Id, [int]$tree.runtime_pid, [int]$tree.child_pid)
    $crashIdentities = @($crashPids | ForEach-Object { Get-PidIdentity $_ })
    Stop-Process -Id $crashLauncher.Id -Force
    Assert-True (Wait-MsoCondition { @($crashIdentities | Where-Object { Test-PidIdentityAlive $_ }).Count -eq 0 }) `
        'launcher crash descendant cleanup'
    Write-Output "CRASH_TEST_PIDS=$($crashPids -join ',')"
    Write-Output 'LAUNCHER_CRASH_JOB_CLEANUP=PASS'

    Remove-Item -LiteralPath (Join-Path $TestRoot 'tree.json') -Force
    Remove-Item -LiteralPath (Join-Path $TestRoot 'launcher.json') -Force
    $unrelated = Start-Process -FilePath $PythonExecutable `
        -ArgumentList (ConvertTo-WindowsCommandLine @('-I', '-c', 'import time; time.sleep(300)')) `
        -WorkingDirectory $TestRoot -WindowStyle Hidden -PassThru
    $owned = New-MsoOwnedProcess -FileName $PythonExecutable -WorkingDirectory $TestRoot `
        -RawArguments (ConvertTo-WindowsCommandLine @(
            '-I', '-c', 'import time; time.sleep(300) # mso_lifecycle_test_child'
        )) -JobName "Local\MSO-Selection-$([Guid]::NewGuid().ToString('N'))"
    $ownership = New-MsoProcessOwnershipRecord -RuntimeRoot $TestRoot `
        -OwnershipId ([Guid]::NewGuid().ToString('N')) -RuntimePid $owned.ProcessId `
        -JobName $owned.JobName -ReleaseVersion 'old-release' -ReleaseRoot $TestRoot `
        -ReleasePython $PythonExecutable -Mode rehearsal -SchedulerTaskName $crashTaskName
    $owned.Resume()
    $selectionIdentityLive = Test-MsoProcessIdentity -Record $ownership.Record
    Write-Output "SELECTION_TEST_IDENTITY_LIVE=$selectionIdentityLive"
    if (-not $selectionIdentityLive) {
        Get-CimInstance Win32_Process -Filter "ProcessId = $($owned.ProcessId)" |
            Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine | Format-List
        $ownership.Record | ConvertTo-Json -Depth 4 | Write-Output
    }
    Assert-True $selectionIdentityLive 'selection test process identity'
    $selectionRejected = $false
    try { Assert-MsoReleaseSelectionSafe -RuntimeRoot $TestRoot -TaskNames @() }
    catch {
        Write-Output "RELEASE_SELECTION_REJECTION_MESSAGE=$($_.Exception.Message)"
        $selectionRejected = $_.Exception.Message -match 'live MSO-owned process'
    }
    Assert-True $selectionRejected 'release selection rejection while daemon alive'
    Write-Output 'RELEASE_SELECTION_WITH_LIVE_DAEMON=REJECTED'
    $owned.Dispose()
    Assert-True (Wait-MsoCondition { -not (Test-PidAlive ([int]$ownership.Record.runtime_pid)) }) `
        'owned selection process stop'
    Set-MsoOwnershipExit -Path $ownership.Path -Status 'EXITED' -ExitCode 0
    Assert-MsoReleaseSelectionSafe -RuntimeRoot $TestRoot -TaskNames @()
    Write-Output 'RELEASE_SELECTION_AFTER_CLEAN_STOP=PASS'
    Assert-True (Test-PidAlive $unrelated.Id) 'unrelated Python survival'
    Write-Output "UNRELATED_PYTHON_PID=$($unrelated.Id)"
    Write-Output 'UNRELATED_PYTHON_SURVIVED=PASS'
    Write-Output 'PAPER_POSITIONS=0'
    Write-Output 'REAL_ORDERS=0'
    Write-Output 'FORMAL_STATUS=NO_GO'
    Write-Output 'RUNTIME_LIFECYCLE_TEST=PASS'
    Write-Output "POWERSHELL_EDITION=$($PSVersionTable.PSEdition)"
    Write-Output "POWERSHELL_VERSION=$($PSVersionTable.PSVersion.ToString())"
}
finally {
    if ($unrelated -and (Test-PidAlive $unrelated.Id)) { Stop-Process -Id $unrelated.Id -Force }
    if ($crashLauncher -and (Test-PidAlive $crashLauncher.Id)) { Stop-Process -Id $crashLauncher.Id -Force }
    Stop-ScheduledTask -TaskName $testTask -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $testTask -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $TestRoot -Recurse -Force -ErrorAction SilentlyContinue
}
