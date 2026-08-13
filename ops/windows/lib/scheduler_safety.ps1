Set-StrictMode -Version 2.0

function Test-MsoTaskActive {
    [CmdletBinding()]
    param($Task)
    return $null -ne $Task -and [string]$Task.State -ne 'Disabled'
}

function Get-MsoActiveSchedulerMode {
    [CmdletBinding()]
    param($RehearsalTask, $FormalTask)
    $rehearsalActive = Test-MsoTaskActive -Task $RehearsalTask
    $formalActive = Test-MsoTaskActive -Task $FormalTask
    if ($rehearsalActive -and $formalActive) { return 'ERROR_BOTH_ACTIVE' }
    if ($rehearsalActive) { return 'rehearsal' }
    if ($formalActive) { return 'formal' }
    return 'none'
}

function Get-MsoSchedulerTaskName {
    [CmdletBinding()]
    param([ValidateSet('rehearsal', 'formal')][string]$Mode)
    if ($Mode -eq 'formal') { return 'MSO-Daily-Formal' }
    return 'MSO-Daily-Rehearsal'
}
