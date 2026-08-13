[CmdletBinding()]
param(
    [ValidateSet('rehearsal', 'formal')][string]$Mode = 'formal',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'Runtime is not initialized.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
foreach ($field in @('release_root', 'release_python', 'release_version', 'release_experiment_lane')) {
    if (-not $config.$field) { throw "Frozen production release field is missing: $field" }
}
$releaseManifest = Join-Path $config.release_root 'release_manifest.json'
if (-not (Test-Path -LiteralPath $releaseManifest -PathType Leaf)) { throw 'Frozen release manifest is missing.' }

function Send-MsoAlert {
    param([string]$Kind, [string]$Title, [string]$Message)
    & $config.release_python -m market_state_observatory.runtime.notifications `
        --kind $Kind --title $Title --message $Message 2>$null | Out-Null
}

function Invoke-SanitizedPython {
    param([string[]]$Arguments, [switch]$WithCredential)
    $credential = $null
    $plainKeyId = $null
    $plainSecret = $null
    if ($WithCredential) {
        $credentialPath = Join-Path $runtimeRoot 'secrets\alpaca.credential.xml'
        if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) { throw 'Alpaca DPAPI credential is missing.' }
        $credential = Import-Clixml -LiteralPath $credentialPath
        $plainKeyId = $credential.UserName
        $plainSecret = $credential.GetNetworkCredential().Password
    }
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $config.release_python
    $startInfo.WorkingDirectory = $config.release_root
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.Environment['MSO_RUNTIME_ROOT'] = $runtimeRoot
    $startInfo.Environment['MSO_RELEASE_ROOT'] = $config.release_root
    $startInfo.Environment['MSO_SOURCE_ROOT'] = $config.repository_root
    if ($WithCredential) {
        $startInfo.Environment['APCA_API_KEY_ID'] = $plainKeyId
        $startInfo.Environment['APCA_API_SECRET_KEY'] = $plainSecret
        $startInfo.Environment['ALPACA_DATA_FEED'] = 'sip'
    }
    foreach ($argument in $Arguments) { [void]$startInfo.ArgumentList.Add($argument) }
    try {
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($WithCredential -and (
            $stdout.Contains($plainKeyId) -or $stdout.Contains($plainSecret) -or
            $stderr.Contains($plainKeyId) -or $stderr.Contains($plainSecret)
        )) { throw 'Child output rejected because credential material was detected.' }
        return [pscustomobject]@{ ExitCode = $process.ExitCode; Stdout = $stdout; Stderr = $stderr }
    }
    finally {
        $startInfo.Environment.Remove('APCA_API_KEY_ID')
        $startInfo.Environment.Remove('APCA_API_SECRET_KEY')
        $credential = $null; $plainKeyId = $null; $plainSecret = $null
        [GC]::Collect()
    }
}

$arguments = @('-m', 'market_state_observatory.runtime.daily_daemon', '--mode', $Mode)
if ($DryRun) { $arguments += '--dry-run' }
try {
    $result = Invoke-SanitizedPython -Arguments $arguments -WithCredential:(-not $DryRun)
}
catch {
    $kind = if ($_.Exception.Message -match 'credential') { 'credential_invalid' } else { 'task_not_started' }
    Send-MsoAlert -Kind $kind -Title 'MSO runtime blocked' -Message 'The frozen data runtime did not start. Review the private operator console.'
    throw
}
$stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
$logPath = Join-Path $runtimeRoot "logs\release-runtime-$stamp.log"
@($result.Stdout, $result.Stderr) | Set-Content -LiteralPath $logPath -Encoding UTF8
if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
if ($result.Stderr) { Write-Error $result.Stderr.TrimEnd() -ErrorAction Continue }
if ($result.ExitCode -ne 0) {
    Send-MsoAlert -Kind 'quality_failed' -Title 'MSO runtime failed' -Message 'The runtime exited nonzero. No public state was updated.'
}
if ($result.ExitCode -ne 0 -or $DryRun -or $Mode -ne 'formal') { exit $result.ExitCode }

$etNow = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'Eastern Standard Time')
$dayRoot = Join-Path $runtimeRoot "data_shadow\$($config.release_experiment_lane)\$($etNow.ToString('yyyy-MM-dd'))"
$quality = Get-ChildItem -LiteralPath $dayRoot -Filter 'DATA_QUALITY.json' -File -Recurse -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $quality) { throw 'Publication blocked: immutable quality artifact is missing.' }
$publish = Invoke-SanitizedPython -Arguments @(
    '-m', 'market_state_observatory.publication.runtime_publisher',
    '--repository', $config.repository_root,
    '--quality', $quality.FullName,
    '--push'
)
@($publish.Stdout, $publish.Stderr) | Set-Content -LiteralPath (Join-Path $runtimeRoot "logs\publication-$stamp.log") -Encoding UTF8
if ($publish.Stdout) { Write-Output $publish.Stdout.TrimEnd() }
if ($publish.Stderr) { Write-Error $publish.Stderr.TrimEnd() -ErrorAction Continue }
if ($publish.ExitCode -ne 0) {
    Send-MsoAlert -Kind 'publication_failed' -Title 'MSO publication failed' -Message 'Fail-closed publication rejected or could not publish the run.'
}
exit $publish.ExitCode
