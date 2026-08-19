[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$name = 'MSO-Daily-Report'
$task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Output "TASK_NAME=$name"
    Write-Output 'TASK_STATUS=ABSENT'
    Write-Output 'SCHEDULER_CHANGED=false'
    exit 0
}
$info = Get-ScheduledTaskInfo -TaskName $name
Write-Output "TASK_NAME=$name"
Write-Output "TASK_STATUS=$($task.State)"
Write-Output "NEXT_RUN=$($info.NextRunTime.ToString('o'))"
Write-Output "LAST_RUN=$($info.LastRunTime.ToString('o'))"
Write-Output "LAST_RESULT=$($info.LastTaskResult)"
Write-Output 'SCHEDULER_CHANGED=false'
