Set-StrictMode -Version 2.0

$script:MsoProcessCompatVersion = '0.4.2'

function ConvertTo-WindowsCommandLineArgument {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Argument)

    if ($Argument.Length -gt 0 -and $Argument -notmatch '[\s"]') {
        return $Argument
    }

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append([char]34)
    $backslashes = 0
    foreach ($character in $Argument.ToCharArray()) {
        if ($character -eq [char]92) {
            $backslashes += 1
            continue
        }
        if ($character -eq [char]34) {
            if ($backslashes -gt 0) {
                [void]$builder.Append([char]92, (2 * $backslashes))
            }
            [void]$builder.Append([char]92)
            [void]$builder.Append([char]34)
        }
        else {
            if ($backslashes -gt 0) {
                [void]$builder.Append([char]92, $backslashes)
            }
            [void]$builder.Append($character)
        }
        $backslashes = 0
    }
    if ($backslashes -gt 0) {
        [void]$builder.Append([char]92, (2 * $backslashes))
    }
    [void]$builder.Append([char]34)
    return $builder.ToString()
}

function ConvertTo-WindowsCommandLine {
    [CmdletBinding()]
    param([AllowEmptyCollection()][string[]]$ArgumentList = @())

    $quoted = @(
        foreach ($argument in $ArgumentList) {
            ConvertTo-WindowsCommandLineArgument -Argument $argument
        }
    )
    return $quoted -join ' '
}

function Set-MsoChildEnvironmentVariable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.ProcessStartInfo]$StartInfo,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
    )
    $StartInfo.EnvironmentVariables[$Name] = $Value
}

function Remove-MsoChildEnvironmentVariable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.ProcessStartInfo]$StartInfo,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($StartInfo.EnvironmentVariables.ContainsKey($Name)) {
        $StartInfo.EnvironmentVariables.Remove($Name)
    }
}

function New-MsoProcessStartInfo {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [AllowEmptyCollection()][string[]]$ArgumentList = @(),
        [hashtable]$ChildEnvironment = @{},
        [string[]]$RemoveEnvironment = @()
    )
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FileName
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.Arguments = ConvertTo-WindowsCommandLine -ArgumentList $ArgumentList
    foreach ($name in $RemoveEnvironment) {
        Remove-MsoChildEnvironmentVariable -StartInfo $startInfo -Name $name
    }
    foreach ($name in $ChildEnvironment.Keys) {
        Set-MsoChildEnvironmentVariable -StartInfo $startInfo -Name $name -Value ([string]$ChildEnvironment[$name])
    }
    return $startInfo
}

function Invoke-MsoChildProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [AllowEmptyCollection()][string[]]$ArgumentList = @(),
        [hashtable]$ChildEnvironment = @{},
        [string[]]$RemoveEnvironment = @()
    )
    $startInfo = New-MsoProcessStartInfo -FileName $FileName -WorkingDirectory $WorkingDirectory `
        -ArgumentList $ArgumentList -ChildEnvironment $ChildEnvironment `
        -RemoveEnvironment $RemoveEnvironment
    try {
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Stdout = $stdout
            Stderr = $stderr
        }
    }
    finally {
        foreach ($name in $ChildEnvironment.Keys) {
            Remove-MsoChildEnvironmentVariable -StartInfo $startInfo -Name $name
        }
    }
}

function Assert-MsoCredentialSafeOutput {
    [CmdletBinding()]
    param(
        [AllowEmptyString()][string]$Stdout,
        [AllowEmptyString()][string]$Stderr,
        [Parameter(Mandatory = $true)][string]$KeyId,
        [Parameter(Mandatory = $true)][string]$Secret
    )
    if ($Stdout.Contains($KeyId) -or $Stdout.Contains($Secret) -or
        $Stderr.Contains($KeyId) -or $Stderr.Contains($Secret)) {
        throw 'Child output rejected because credential material was detected.'
    }
}

function Resolve-MsoBootstrapPython {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Candidate)

    $command = Get-Command $Candidate -ErrorAction SilentlyContinue
    $resolved = if ($command) { $command.Source } else { $Candidate }
    if (-not $resolved -or -not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw 'Bootstrap Python executable does not exist.'
    }
    $resolved = (Resolve-Path -LiteralPath $resolved).Path
    if ($resolved -match '[\\/]Microsoft[\\/]WindowsApps[\\/]python(?:3)?\.exe$') {
        throw 'Microsoft WindowsApps Python alias is not a valid bootstrap interpreter.'
    }
    $probe = Invoke-MsoChildProcess -FileName $resolved -WorkingDirectory ([IO.Path]::GetTempPath()) `
        -ArgumentList @('--version') -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
    if ($probe.ExitCode -ne 0) {
        throw 'Bootstrap Python executable failed its version probe.'
    }
    return $resolved
}

function Resolve-MsoRuntimePython {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Config,
        [Parameter(Mandatory = $true)][string]$RuntimeRoot
    )
    foreach ($field in @('release_root', 'release_python', 'release_version', 'release_experiment_lane')) {
        if (-not $Config.$field) { throw "Frozen production release field is missing: $field" }
    }
    $releaseRoot = [IO.Path]::GetFullPath([string]$Config.release_root).TrimEnd([char]92)
    $releasePython = [IO.Path]::GetFullPath([string]$Config.release_python)
    if (-not (Test-Path -LiteralPath $releaseRoot -PathType Container)) {
        throw 'Frozen release root does not exist.'
    }
    if (-not (Test-Path -LiteralPath $releasePython -PathType Leaf)) {
        throw 'Frozen release Python does not exist.'
    }
    if (-not $releasePython.StartsWith($releaseRoot + [char]92, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Frozen release Python must be located below release_root.'
    }
    if ($releasePython -match '[\\/]Microsoft[\\/]WindowsApps[\\/]python(?:3)?\.exe$') {
        throw 'WindowsApps Python alias is forbidden for frozen runtime execution.'
    }
    $environment = @{
        MSO_RUNTIME_ROOT = $RuntimeRoot
        MSO_RELEASE_ROOT = $releaseRoot
    }
    $integrity = Invoke-MsoChildProcess -FileName $releasePython -WorkingDirectory $releaseRoot `
        -ArgumentList @('-I', '-m', 'market_state_observatory.runtime.release_identity', '--verify-release') `
        -ChildEnvironment $environment -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
    if ($integrity.ExitCode -ne 0 -or $integrity.Stdout -notmatch 'RELEASE_INTEGRITY=PASS') {
        throw 'Frozen release integrity verification failed.'
    }
    $identityCode = @'
import json, sys
import market_state_observatory as module
print(json.dumps({"executable": sys.executable, "module_file": module.__file__}))
'@
    $identityResult = Invoke-MsoChildProcess -FileName $releasePython -WorkingDirectory $releaseRoot `
        -ArgumentList @('-I', '-c', $identityCode) -ChildEnvironment $environment `
        -RemoveEnvironment @('PYTHONPATH', 'PYTHONHOME')
    if ($identityResult.ExitCode -ne 0) { throw 'Frozen Python identity probe failed.' }
    $identity = $identityResult.Stdout | ConvertFrom-Json
    $actualPython = [IO.Path]::GetFullPath([string]$identity.executable)
    $modulePath = [IO.Path]::GetFullPath([string]$identity.module_file)
    if (-not $actualPython.Equals($releasePython, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Frozen child resolved an unexpected Python executable.'
    }
    if (-not $modulePath.StartsWith($releaseRoot + [char]92, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'market_state_observatory was imported outside the frozen release.'
    }
    return [pscustomobject]@{
        Python = $releasePython
        ReleaseRoot = $releaseRoot
        ModulePath = $modulePath
        IntegrityOutput = $integrity.Stdout.Trim()
    }
}
