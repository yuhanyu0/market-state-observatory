[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Install,
    [switch]$ReviewedWhatIf,
    [string]$CandidateReleaseRoot
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')
$taskName = 'MSO-Preclose-Candidate-Shadow'
$powerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$runner = if ($CandidateReleaseRoot) {
    Join-Path ([IO.Path]::GetFullPath($CandidateReleaseRoot)) 'run_preclose_candidate_shadow.ps1'
} else {
    Join-Path $PSScriptRoot 'run_preclose_candidate_shadow.ps1'
}
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Preclose candidate runner is missing.' }
$arguments = ConvertTo-WindowsCommandLine -ArgumentList @(
    '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
    '-File', $runner
)

Write-Output "TASK_NAME=$taskName"
Write-Output 'SCHEDULE=15:46 America/New_York on weekdays; runner validates immutable XNYS evidence'
Write-Output "EXECUTABLE=$powerShell"
Write-Output "ARGUMENTS=$arguments"
Write-Output 'MODE=PROSPECTIVE_CANDIDATE_SHADOW'
Write-Output 'BROKER_CLIENT=false'
Write-Output 'ORDER_OBJECT=false'
Write-Output 'PAPER_POSITIONS=0'
Write-Output 'REAL_ORDERS=0'

if ($WhatIfPreference) {
    Write-Output 'INSTALL_PREVIEW_ONLY=true'
    Write-Output 'SCHEDULER_CHANGED=false'
    exit 0
}
if (-not $Install) {
    Write-Output 'INSTALL_REQUESTED=false'
    Write-Output 'Run -Install -WhatIf first. Installation requires -Install -ReviewedWhatIf.'
    exit 0
}
if (-not $ReviewedWhatIf) { throw 'INSTALL_REJECTED: a reviewed -WhatIf preview is required.' }
if (-not $CandidateReleaseRoot) { throw 'INSTALL_REJECTED: a frozen candidate release is required.' }
$manifest = Join-Path ([IO.Path]::GetFullPath($CandidateReleaseRoot)) 'release_manifest.json'
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
    throw 'INSTALL_REJECTED: candidate release manifest is missing.'
}
$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments `
    -WorkingDirectory ([IO.Path]::GetFullPath($CandidateReleaseRoot))
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '15:46'
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description 'MSO prospective candidate evidence only. No positions or orders.'
if ($PSCmdlet.ShouldProcess($taskName, 'Register candidate-only preclose task')) {
    Register-ScheduledTask -TaskName $taskName -InputObject $task | Out-Null
    Write-Output 'TASK_STATUS=INSTALLED'
}
