[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Install,
    [switch]$ReviewedWhatIf,
    [string]$AnalysisReleaseRoot
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')
$taskName = 'MSO-Daily-Report'
$powerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$runner = if ($AnalysisReleaseRoot) {
    Join-Path ([IO.Path]::GetFullPath($AnalysisReleaseRoot)) 'run_daily_report.ps1'
} else {
    Join-Path $PSScriptRoot 'run_daily_report.ps1'
}
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Daily report runner is missing.' }
$arguments = ConvertTo-WindowsCommandLine -ArgumentList @(
    '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
    '-File', $runner, '-Mode', 'OBSERVATION_ONLY'
)

Write-Output "TASK_NAME=$taskName"
Write-Output 'SCHEDULE=16:15 America/New_York on weekdays; runner verifies XNYS session'
Write-Output "EXECUTABLE=$powerShell"
Write-Output "ARGUMENTS=$arguments"
Write-Output 'INDEPENDENT_FROM_CAPTURE=true'
Write-Output 'CREDENTIALS_REQUIRED=false'
Write-Output 'NETWORK_REQUIRED=false'
Write-Output 'PUBLIC_PUSH=false'
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
if (-not $ReviewedWhatIf) {
    throw 'INSTALL_REJECTED: a reviewed -WhatIf preview is required.'
}
if (-not $AnalysisReleaseRoot) {
    throw 'INSTALL_REJECTED: -AnalysisReleaseRoot must identify a frozen candidate release.'
}
$releaseManifest = Join-Path ([IO.Path]::GetFullPath($AnalysisReleaseRoot)) 'release_manifest.json'
if (-not (Test-Path -LiteralPath $releaseManifest -PathType Leaf)) {
    throw 'INSTALL_REJECTED: frozen analysis release manifest is missing.'
}

$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments -WorkingDirectory ([IO.Path]::GetFullPath($AnalysisReleaseRoot))
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '16:15'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'MSO private completed-run observation report. No network, positions, or orders.'
if ($PSCmdlet.ShouldProcess($taskName, 'Register read-only Market State Observatory report task')) {
    Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
    Write-Output 'TASK_STATUS=INSTALLED'
}
