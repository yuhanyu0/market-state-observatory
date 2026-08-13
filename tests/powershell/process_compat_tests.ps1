[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$PythonExecutable)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $root 'ops\windows\lib\process_compat.ps1')

function Assert-Equal {
    param($Actual, $Expected, [string]$Name)
    if ($Actual -ne $Expected) { throw "$Name failed: expected=[$Expected] actual=[$Actual]" }
}

$python = Resolve-MsoBootstrapPython -Candidate $PythonExecutable
$working = Join-Path ([IO.Path]::GetTempPath()) "mso process compat $([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $working | Out-Null
try {
    $arguments = @(
        '',
        'plain',
        'contains space',
        "contains`ttab",
        'embedded"quote',
        'C:\Program Files\Market State Observatory\',
        'C:\plain\trailing\',
        'slashes\\before"quote',
        '{"path":"C:\\Program Files\\MSO\\"}'
    )
    $argvCode = 'import json,sys; print(json.dumps(sys.argv[1:]))'
    $roundTrip = Invoke-MsoChildProcess -FileName $python -WorkingDirectory $working `
        -ArgumentList (@('-I', '-c', $argvCode) + $arguments) `
        -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
    Assert-Equal $roundTrip.ExitCode 0 'argument roundtrip exit'
    $actualArguments = $roundTrip.Stdout | ConvertFrom-Json
    Assert-Equal $actualArguments.Count $arguments.Count 'argument roundtrip count'
    for ($index = 0; $index -lt $arguments.Count; $index += 1) {
        Assert-Equal ([string]$actualArguments[$index]) ([string]$arguments[$index]) `
            "argument roundtrip index $index"
    }

    $credentialCode = @'
import json, os
print(json.dumps({
    "key": "PRESENT" if os.environ.get("APCA_API_KEY_ID") else "ABSENT",
    "secret": "PRESENT" if os.environ.get("APCA_API_SECRET_KEY") else "ABSENT"
}))
'@
    $parentKey = $env:APCA_API_KEY_ID
    $parentSecret = $env:APCA_API_SECRET_KEY
    Remove-Item Env:MSO_TEST_EPHEMERAL -ErrorAction SilentlyContinue
    $presence = Invoke-MsoChildProcess -FileName $python -WorkingDirectory $working `
        -ArgumentList @('-I', '-c', $credentialCode) -ChildEnvironment @{
            APCA_API_KEY_ID = 'synthetic-key-for-process-test'
            APCA_API_SECRET_KEY = 'synthetic-secret-for-process-test'
            MSO_TEST_EPHEMERAL = 'child-only'
        }
    Assert-Equal $presence.ExitCode 0 'credential presence exit'
    $presencePayload = $presence.Stdout | ConvertFrom-Json
    Assert-Equal $presencePayload.key 'PRESENT' 'credential key presence'
    Assert-Equal $presencePayload.secret 'PRESENT' 'credential secret presence'
    Assert-Equal $env:MSO_TEST_EPHEMERAL $null 'child environment cleanup'
    Assert-Equal $env:APCA_API_KEY_ID $parentKey 'parent key unchanged'
    Assert-Equal $env:APCA_API_SECRET_KEY $parentSecret 'parent secret unchanged'

    $leakRejected = $false
    try {
        Assert-MsoCredentialSafeOutput -Stdout 'synthetic-key-for-process-test' -Stderr '' `
            -KeyId 'synthetic-key-for-process-test' -Secret 'synthetic-secret-for-process-test'
    }
    catch { $leakRejected = $_.Exception.Message -match 'credential material' }
    Assert-Equal $leakRejected $true 'credential leak rejection'

    $captureCode = 'import sys; print("STDOUT_CAPTURED"); print("STDERR_CAPTURED", file=sys.stderr); raise SystemExit(23)'
    $captured = Invoke-MsoChildProcess -FileName $python -WorkingDirectory $working `
        -ArgumentList @('-I', '-c', $captureCode)
    Assert-Equal $captured.ExitCode 23 'child exit propagation'
    Assert-Equal $captured.Stdout.Trim() 'STDOUT_CAPTURED' 'stdout capture'
    Assert-Equal $captured.Stderr.Trim() 'STDERR_CAPTURED' 'stderr capture'

    Assert-Equal @(Get-ChildItem -LiteralPath $working -File -Recurse).Count 0 'no-log path'
    $forbidden = Get-ChildItem (Join-Path $root 'ops\windows') -Filter *.ps1 -File -Recurse |
        Select-String -Pattern '\.ArgumentList|\.Environment\[|\.Environment\.Remove'
    Assert-Equal @($forbidden).Count 0 'PowerShell 7-only ProcessStartInfo API audit'

    Write-Output "PROCESS_COMPAT_TEST=PASS"
    Write-Output "POWERSHELL_EDITION=$($PSVersionTable.PSEdition)"
    Write-Output "POWERSHELL_VERSION=$($PSVersionTable.PSVersion.ToString())"
    Write-Output "ARGUMENT_ROUNDTRIP=PASS"
    Write-Output "CREDENTIAL_PRESENCE=PASS"
    Write-Output "CREDENTIAL_LEAK_REJECTION=PASS"
    Write-Output "CHILD_EXIT_CODE_PROPAGATION=PASS"
    Write-Output "STDOUT_STDERR_CAPTURE=PASS"
    Write-Output "NO_LOG_PATH=PASS"
    Write-Output "ENVIRONMENT_CLEANUP=PASS"
}
finally {
    Remove-Item -LiteralPath $working -Recurse -Force -ErrorAction SilentlyContinue
}
