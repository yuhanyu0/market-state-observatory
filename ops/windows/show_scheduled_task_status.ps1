[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')
. (Join-Path $PSScriptRoot 'lib\scheduler_safety.ps1')

function Get-MsoTaskStatus {
    param([string]$Name)
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if (-not $task) {
        return [pscustomobject]@{
            Name = $Name; Display = 'ABSENT'; Active = $false
            NextRun = $null; LastRun = $null; LastResult = $null; Task = $null
        }
    }
    $info = Get-ScheduledTaskInfo -TaskName $Name
    $disabled = [string]$task.State -eq 'Disabled'
    return [pscustomobject]@{
        Name = $Name; Display = if ($disabled) { 'DISABLED' } else { 'INSTALLED' }
        Active = -not $disabled
        NextRun = $info.NextRunTime; LastRun = $info.LastRunTime; LastResult = $info.LastTaskResult
        Task = $task
    }
}

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
$config = if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
} else { $null }
$rehearsal = Get-MsoTaskStatus -Name 'MSO-Daily-Rehearsal'
$formal = Get-MsoTaskStatus -Name 'MSO-Daily-Formal'
$activeMode = Get-MsoActiveSchedulerMode `
    -RehearsalTask $rehearsal.Task -FormalTask $formal.Task
$selected = if ($formal.Active) { $formal } elseif ($rehearsal.Active) { $rehearsal } else { $null }
$manifest = $null
if ($config -and $config.release_root) {
    $manifestPath = Join-Path $config.release_root 'release_manifest.json'
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    }
}
$authorizationPath = Join-Path $runtimeRoot 'promotion\formal_data_shadow_authorization.json'
$promotionStatus = 'NOT_AUTHORIZED'
if (Test-Path -LiteralPath $authorizationPath -PathType Leaf) {
    $promotionStatus = 'INVALID'
    try {
        $runtime = Resolve-MsoRuntimePython -Config $config -RuntimeRoot $runtimeRoot
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
        if ($verification.ExitCode -eq 0) { $promotionStatus = 'AUTHORIZED' }
    } catch { $promotionStatus = 'INVALID' }
}
$liveOwned = @(Get-MsoLiveOwnedProcesses -RuntimeRoot $runtimeRoot)
$lockState = Get-MsoRuntimeLockState -RuntimeRoot $runtimeRoot
$processState = if ($liveOwned.Count -gt 0) { 'ACTIVE_VERIFIED' } elseif ($lockState.State -eq 'ABSENT') { 'INACTIVE' } else { 'STALE_OR_INCONSISTENT' }

Write-Output "REHEARSAL_TASK=$($rehearsal.Display)"
Write-Output "FORMAL_TASK=$($formal.Display)"
Write-Output "ACTIVE_MODE=$activeMode"
Write-Output "RELEASE_VERSION=$(if($config){$config.release_version}else{'UNAVAILABLE'})"
Write-Output "RELEASE_SHA=$(if($manifest){$manifest.git_sha}else{'UNAVAILABLE'})"
Write-Output "EXPERIMENT_LANE=$(if($config){$config.release_experiment_lane}else{'UNAVAILABLE'})"
Write-Output "NEXT_RUN=$(if($selected -and $selected.NextRun){$selected.NextRun.ToString('o')}else{'NONE'})"
Write-Output "LAST_RUN=$(if($selected -and $selected.LastRun){$selected.LastRun.ToString('o')}else{'NONE'})"
Write-Output "LAST_RESULT=$(if($selected -and $null -ne $selected.LastResult){$selected.LastResult}else{'NONE'})"
Write-Output "PROMOTION_STATUS=$promotionStatus"
Write-Output "RUNTIME_PROCESS_STATE=$processState"
Write-Output "LIVE_OWNED_PROCESS_COUNT=$($liveOwned.Count)"
Write-Output "RUNTIME_LOCK_STATE=$($lockState.State)"
if ($activeMode -eq 'ERROR_BOTH_ACTIVE') {
    $alertPath = Join-Path $runtimeRoot "alerts\scheduler-both-active-$([Guid]::NewGuid().ToString('N')).json"
    [ordered]@{
        kind = 'scheduler_both_active'
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        action_required = 'Disable one scheduler task immediately.'
        paper_positions = 0
        real_orders = 0
    } | ConvertTo-Json | Set-Content -LiteralPath $alertPath -Encoding UTF8
    exit 1
}
