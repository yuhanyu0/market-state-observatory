[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$installPath = Join-Path $root 'ops\windows\install_scheduled_tasks.ps1'
$smokePath = Join-Path $root 'ops\windows\run_scheduled_task_smoke_test.ps1'
$promotePath = Join-Path $root 'ops\windows\promote_to_formal_data_shadow.ps1'
$helperPath = Join-Path $root 'ops\windows\lib\scheduler_safety.ps1'
$install = Get-Content -LiteralPath $installPath -Raw
$smoke = Get-Content -LiteralPath $smokePath -Raw
$promote = Get-Content -LiteralPath $promotePath -Raw
. $helperPath

if ($install -notmatch "\[string\]\`$Mode = 'rehearsal'") {
    throw 'Default scheduler mode is not rehearsal.'
}
if ($install -notmatch 'MSO-Daily-Rehearsal' -or $install -notmatch 'MSO-Daily-Formal') {
    throw 'Separate rehearsal and formal task names are missing.'
}
if ($install -notmatch '--verify-authorization') {
    throw 'Formal scheduler authorization verification is missing.'
}
if ($install -notmatch 'FORMAL_SCHEDULER_INSTALL_REJECTED') {
    throw 'Formal scheduler fail-closed rejection is missing.'
}
if ($smoke -notmatch 'Get-ScheduledTask' -or $smoke -notmatch 'REGISTERED_ACTION') {
    throw 'Scheduled-task smoke does not inspect the registered task action.'
}
if ($promote -match '(?im)param\s*\([^)]*(Force|Threshold)') {
    throw 'Promotion script exposes a force or threshold override.'
}
$ready = [pscustomobject]@{ State = 'Ready' }
$disabled = [pscustomobject]@{ State = 'Disabled' }
if ((Get-MsoActiveSchedulerMode -RehearsalTask $ready -FormalTask $ready) -ne 'ERROR_BOTH_ACTIVE') {
    throw 'Both-active scheduler state was not rejected.'
}
if ((Get-MsoActiveSchedulerMode -RehearsalTask $ready -FormalTask $disabled) -ne 'rehearsal') {
    throw 'Rehearsal scheduler state was not identified.'
}

$failed = $false
foreach ($path in @($installPath, $smokePath, $promotePath, $helperPath)) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $path, [ref]$tokens, [ref]$errors
    )
    if ($errors.Count) { $failed = $true; $errors | Write-Error }
}
if ($failed) { exit 1 }

Write-Output 'SCHEDULER_SAFETY_TEST=PASS'
Write-Output "POWERSHELL_EDITION=$($PSVersionTable.PSEdition)"
Write-Output "POWERSHELL_VERSION=$($PSVersionTable.PSVersion.ToString())"
Write-Output 'DEFAULT_MODE=rehearsal'
Write-Output 'FORMAL_PROMOTION_GATE=PASS'
Write-Output 'REGISTERED_ACTION_INSPECTION=PASS'
Write-Output 'BOTH_ACTIVE_REJECTION=PASS'
