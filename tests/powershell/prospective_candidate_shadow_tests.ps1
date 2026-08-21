$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runner = Join-Path $repository 'ops\windows\run_preclose_candidate_shadow.ps1'
$installer = Join-Path $repository 'ops\windows\install_preclose_candidate_shadow_task.ps1'

$before = Get-ScheduledTask -TaskName 'MSO-Preclose-Candidate-Shadow' -ErrorAction SilentlyContinue
$runnerOutput = @(& $runner -WhatIf)
if ($LASTEXITCODE -ne 0) { throw 'Preclose candidate WhatIf failed.' }
foreach ($expected in @(
    'EXECUTION_MODE=PROSPECTIVE_CANDIDATE_SHADOW',
    'BROKER_CLIENT=false',
    'ORDER_OBJECT=false',
    'PAPER_POSITIONS=0',
    'REAL_ORDERS=0',
    'NETWORK_CALLED=false',
    'SCHEDULER_CHANGED=false'
)) {
    if ($runnerOutput -notcontains $expected) { throw "Runner WhatIf missing: $expected" }
}
$installOutput = @(& $installer -WhatIf)
if ($LASTEXITCODE -ne 0) { throw 'Preclose task installer WhatIf failed.' }
if ($installOutput -notcontains 'INSTALL_PREVIEW_ONLY=true') {
    throw 'Installer did not remain preview-only.'
}
$after = Get-ScheduledTask -TaskName 'MSO-Preclose-Candidate-Shadow' -ErrorAction SilentlyContinue
if (($null -eq $before) -ne ($null -eq $after)) {
    throw 'Preclose task installation state changed during WhatIf.'
}
Write-Output 'PRECLOSE_CANDIDATE_POWERSHELL_TESTS=PASS'
Write-Output 'SCHEDULER_CHANGED=false'
Write-Output 'PAPER_POSITIONS=0'
Write-Output 'REAL_ORDERS=0'
