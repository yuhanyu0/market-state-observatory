[CmdletBinding(SupportsShouldProcess)]
param()

$taskName = 'MSO-Daily-Runtime'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    if ($PSCmdlet.ShouldProcess($taskName, 'Unregister scheduled task')) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Output "TASK_REMOVED=$taskName"
    }
} else {
    Write-Output "TASK_NOT_FOUND=$taskName"
}
