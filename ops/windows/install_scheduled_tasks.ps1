[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet('rehearsal', 'formal')][string]$Mode = 'rehearsal',
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')
. (Join-Path $PSScriptRoot 'lib\scheduler_safety.ps1')

function Get-MsoNextWeekdayTrigger {
    param([datetime]$Now = (Get-Date))
    $candidate = $Now.Date.AddHours(9).AddMinutes(20)
    if ($candidate -le $Now) { $candidate = $candidate.AddDays(1) }
    while ($candidate.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) {
        $candidate = $candidate.AddDays(1)
    }
    return $candidate
}

$currentZone = [System.TimeZoneInfo]::Local.Id
if ($currentZone -notin @('Eastern Standard Time', 'America/New_York')) {
    throw "Task trigger requires the Windows system timezone to be Eastern Time; current=$currentZone"
}
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$runtimeConfig = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $runtimeConfig -PathType Leaf)) {
    throw 'Runtime is not initialized. Run initialize_runtime.ps1 first.'
}
$config = Get-Content -LiteralPath $runtimeConfig -Raw | ConvertFrom-Json
foreach ($field in @('release_root', 'release_launcher', 'release_python', 'release_version', 'release_experiment_lane')) {
    if (-not $config.$field) { throw "Frozen production release field is missing: $field" }
}
if (-not (Test-Path -LiteralPath $config.release_launcher -PathType Leaf)) {
    throw 'Frozen production release launcher is missing.'
}
if ($config.paper_positions_allowed -ne $false -or $config.real_orders_allowed -ne $false) {
    throw 'Scheduler installation requires paper_positions_allowed=false and real_orders_allowed=false.'
}

$runtime = Resolve-MsoRuntimePython -Config $config -RuntimeRoot $runtimeRoot
$taskName = Get-MsoSchedulerTaskName -Mode $Mode
$otherTaskName = if ($Mode -eq 'formal') { 'MSO-Daily-Rehearsal' } else { 'MSO-Daily-Formal' }
$powerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$argumentList = @(
    '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
    '-File', [string]$config.release_launcher, '-Mode', $Mode, '-ScheduledTaskName', $taskName
)
$arguments = ConvertTo-WindowsCommandLine -ArgumentList $argumentList
$nextTrigger = Get-MsoNextWeekdayTrigger

Write-Output "TASK_NAME=$taskName"
Write-Output "TASK_MODE=$Mode"
Write-Output "EXECUTABLE=$powerShell"
Write-Output "ARGUMENTS=$arguments"
Write-Output "WORKING_DIRECTORY=$($config.release_root)"
Write-Output "RELEASE_VERSION=$($config.release_version)"
Write-Output "RELEASE_ROOT=$($config.release_root)"
Write-Output "EXPERIMENT_LANE=$($config.release_experiment_lane)"
Write-Output "NEXT_TRIGGER=$($nextTrigger.ToString('o'))"
Write-Output "PAPER_POSITIONS_ALLOWED=$($config.paper_positions_allowed.ToString().ToLowerInvariant())"
Write-Output "REAL_ORDERS_ALLOWED=$($config.real_orders_allowed.ToString().ToLowerInvariant())"

if ($Mode -eq 'formal') {
    $verification = Invoke-MsoChildProcess -FileName $runtime.Python `
        -WorkingDirectory $runtime.ReleaseRoot `
        -ArgumentList @(
            '-I', '-m', 'market_state_observatory.runtime.formal_promotion',
            '--verify-authorization', '--runtime-root', $runtimeRoot
        ) `
        -ChildEnvironment @{
            MSO_RUNTIME_ROOT = $runtimeRoot
            MSO_RELEASE_ROOT = $runtime.ReleaseRoot
        } `
        -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
    if ($verification.Stdout) { Write-Output $verification.Stdout.TrimEnd() }
    if ($verification.ExitCode -ne 0) {
        throw 'FORMAL_SCHEDULER_INSTALL_REJECTED: valid GO promotion artifact required.'
    }
}

$otherTask = Get-ScheduledTask -TaskName $otherTaskName -ErrorAction SilentlyContinue
if ($Mode -eq 'rehearsal' -and (Test-MsoTaskActive $otherTask)) {
    throw 'REHEARSAL_SCHEDULER_INSTALL_REJECTED: formal task is active.'
}

if (-not $Install -and -not $WhatIfPreference) {
    Write-Output 'INSTALL_REQUESTED=false'
    Write-Output 'Use -Install after reviewing, or -Install -WhatIf for a no-change preview.'
    exit 0
}
if ($WhatIfPreference) {
    Write-Output 'INSTALL_PREVIEW_ONLY=true'
    Write-Output 'SCHEDULER_CHANGED=false'
    exit 0
}

$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments `
    -WorkingDirectory $config.release_root
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '09:20'
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 9)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$description = "Market State Observatory $Mode SIP data-only runtime. No positions or orders."
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description $description

if ($PSCmdlet.ShouldProcess($taskName, "Register $Mode Market State Observatory task")) {
    if ($Mode -eq 'formal' -and (Test-MsoTaskActive $otherTask)) {
        Disable-ScheduledTask -TaskName $otherTaskName | Out-Null
        Write-Output "TASK_DISABLED=$otherTaskName"
    }
    Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
    $rehearsal = Get-ScheduledTask -TaskName 'MSO-Daily-Rehearsal' -ErrorAction SilentlyContinue
    $formal = Get-ScheduledTask -TaskName 'MSO-Daily-Formal' -ErrorAction SilentlyContinue
    if ((Test-MsoTaskActive $rehearsal) -and (Test-MsoTaskActive $formal)) {
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        throw 'Scheduler safety invariant failed: rehearsal and formal tasks cannot both be active.'
    }
    & (Join-Path $PSScriptRoot 'run_scheduled_task_smoke_test.ps1') -ExpectedMode $Mode
    if ($LASTEXITCODE -ne 0) {
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        throw 'Registered scheduled task dry-run smoke test failed; task was disabled.'
    }
    Write-Output "TASK_STATUS=INSTALLED"
}
