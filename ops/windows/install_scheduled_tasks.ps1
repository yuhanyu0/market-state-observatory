[CmdletBinding(SupportsShouldProcess)]
param([switch]$Install)

$ErrorActionPreference = 'Stop'
$currentZone = [System.TimeZoneInfo]::Local.Id
if ($currentZone -notin @('Eastern Standard Time', 'America/New_York')) {
    throw "Task trigger requires the Windows system timezone to be Eastern Time; current=$currentZone"
}
$taskName = 'MSO-Daily-Runtime'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$runtimeConfig = Join-Path $runtimeRoot 'runtime_paths.json'
$previewRequested = $WhatIfPreference
if (-not (Test-Path -LiteralPath $runtimeConfig) -and -not $previewRequested) {
    throw 'Runtime is not initialized. Run initialize_runtime.ps1 first.'
}
$repositoryRoot = if (Test-Path -LiteralPath $runtimeConfig) {
    (Get-Content -LiteralPath $runtimeConfig -Raw | ConvertFrom-Json).repository_root
} else {
    (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
$scriptPath = (Resolve-Path (Join-Path $PSScriptRoot 'run_daily_runtime.ps1')).Path
$powerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode formal"

$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments -WorkingDirectory $repositoryRoot
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '09:20'
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 9)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Market State Observatory private SIP data-only runtime. No positions or orders.'

if ($WhatIfPreference -and -not $Install) { $Install = $true }
if (-not $Install) {
    Write-Output 'INSTALL_REQUESTED=false'
    Write-Output "TASK_NAME=$taskName"
    Write-Output 'Use -Install after reviewing, or -Install -WhatIf for a no-change preview.'
    exit 0
}
if ($previewRequested -and -not (Test-Path -LiteralPath $runtimeConfig)) {
    Write-Output 'RUNTIME_STATUS=NOT_INITIALIZED_PREVIEW_ONLY'
}
if ($PSCmdlet.ShouldProcess($taskName, 'Register Market State Observatory daily runtime task')) {
    Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
    & (Join-Path $PSScriptRoot 'run_scheduled_task_smoke_test.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Scheduled task dry-run smoke test failed.' }
    Write-Output "TASK_NAME=$taskName"
    Write-Output 'TASK_STATUS=INSTALLED'
}
