[CmdletBinding()]
param(
    [ValidateSet('rehearsal', 'formal')][string]$ExpectedMode = 'rehearsal',
    [switch]$DefinitionOnly
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')
. (Join-Path $PSScriptRoot 'lib\scheduler_safety.ps1')

$taskName = Get-MsoSchedulerTaskName -Mode $ExpectedMode
$otherName = if ($ExpectedMode -eq 'formal') { 'MSO-Daily-Rehearsal' } else { 'MSO-Daily-Formal' }
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'Runtime is not initialized.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json

$registered = $false
if ($DefinitionOnly) {
    $executable = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $arguments = ConvertTo-WindowsCommandLine -ArgumentList @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
        '-File', [string]$config.release_launcher, '-Mode', $ExpectedMode,
        '-ScheduledTaskName', $taskName
    )
    $workingDirectory = [string]$config.release_root
} else {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Output 'SCHEDULED_TASK_SMOKE_TEST=NOT_INSTALLED'
        exit 2
    }
    $registered = $true
    $action = @($task.Actions)[0]
    $executable = [string]$action.Execute
    $arguments = [string]$action.Arguments
    $workingDirectory = [string]$action.WorkingDirectory
    $otherTask = Get-ScheduledTask -TaskName $otherName -ErrorAction SilentlyContinue
    if ((Test-MsoTaskActive $task) -and (Test-MsoTaskActive $otherTask)) {
        throw 'SCHEDULED_TASK_SMOKE_TEST=FAIL reason=both_tasks_active'
    }
}

$expectedModeToken = "-Mode $ExpectedMode"
$oppositeMode = if ($ExpectedMode -eq 'formal') { 'rehearsal' } else { 'formal' }
if (-not $arguments.Contains($expectedModeToken)) {
    throw "SCHEDULED_TASK_SMOKE_TEST=FAIL reason=missing_$($ExpectedMode)_mode"
}
if ($arguments.Contains("-Mode $oppositeMode")) {
    throw "SCHEDULED_TASK_SMOKE_TEST=FAIL reason=contains_$($oppositeMode)_mode"
}
if (-not $arguments.Contains("-ScheduledTaskName $taskName")) {
    throw 'SCHEDULED_TASK_SMOKE_TEST=FAIL reason=task_identity_missing'
}
if (-not $workingDirectory.Equals([string]$config.release_root, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'SCHEDULED_TASK_SMOKE_TEST=FAIL reason=working_directory_not_release_root'
}

$beforeFormal = @(Get-ChildItem (Join-Path $runtimeRoot 'data_shadow') -File -Recurse `
    -ErrorAction SilentlyContinue).Count
$result = Invoke-MsoChildProcess -FileName $executable -WorkingDirectory $workingDirectory `
    -RawArguments ($arguments + ' -DryRun')
$afterFormal = @(Get-ChildItem (Join-Path $runtimeRoot 'data_shadow') -File -Recurse `
    -ErrorAction SilentlyContinue).Count
if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
if ($result.Stderr) { Write-Error $result.Stderr.TrimEnd() -ErrorAction Continue }
if ($result.ExitCode -ne 0) { throw 'SCHEDULED_TASK_SMOKE_TEST=FAIL reason=dry_run_nonzero' }
if ($result.Stdout -notmatch '"network_called": false') {
    throw 'SCHEDULED_TASK_SMOKE_TEST=FAIL reason=network_contract_missing'
}
if ($result.Stdout -notmatch '"paper_positions": 0' -or $result.Stdout -notmatch '"real_orders": 0') {
    throw 'SCHEDULED_TASK_SMOKE_TEST=FAIL reason=position_order_contract_missing'
}
if ($afterFormal -ne $beforeFormal) {
    throw 'SCHEDULED_TASK_SMOKE_TEST=FAIL reason=formal_data_shadow_created'
}
Write-Output 'SCHEDULED_TASK_SMOKE_TEST=PASS'
Write-Output "TASK_NAME=$taskName"
Write-Output "TASK_MODE=$ExpectedMode"
Write-Output "REGISTERED_ACTION=$($registered.ToString().ToLowerInvariant())"
Write-Output "DEFINITION_ONLY=$($DefinitionOnly.ToString().ToLowerInvariant())"
Write-Output 'NETWORK_CALLED=false'
Write-Output 'FORMAL_DATA_SHADOW_CREATED=false'
Write-Output 'PAPER_POSITIONS=0'
Write-Output 'REAL_ORDERS=0'
