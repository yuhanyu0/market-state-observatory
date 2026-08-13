[CmdletBinding()]
param()

$taskName = 'MSO-Daily-Runtime'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    [ordered]@{ task_name = $taskName; status = 'NOT_INSTALLED'; next_run_time = $null } | ConvertTo-Json
    exit 1
}
$info = Get-ScheduledTaskInfo -TaskName $taskName
[ordered]@{
    task_name = $taskName
    status = $task.State.ToString()
    next_run_time = $info.NextRunTime.ToString('o')
    last_run_time = $info.LastRunTime.ToString('o')
    last_task_result = $info.LastTaskResult
    multiple_instances = $task.Settings.MultipleInstances.ToString()
    wake_to_run = $task.Settings.WakeToRun
    start_when_available = $task.Settings.StartWhenAvailable
} | ConvertTo-Json
