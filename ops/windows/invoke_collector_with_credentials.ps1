[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string[]]$CollectorArguments,
    [switch]$NoLog
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
$credentialPath = Join-Path $runtimeRoot 'secrets\alpaca.credential.xml'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Runtime configuration is missing.' }
if (-not (Test-Path -LiteralPath $credentialPath)) { throw 'Alpaca DPAPI credential is missing.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$credential = Import-Clixml -LiteralPath $credentialPath
$plainKeyId = $credential.UserName
$plainSecret = $credential.GetNetworkCredential().Password
$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $config.python_executable
$startInfo.UseShellExecute = $false
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.CreateNoWindow = $true
$startInfo.WorkingDirectory = $config.repository_root
$startInfo.Environment['APCA_API_KEY_ID'] = $plainKeyId
$startInfo.Environment['APCA_API_SECRET_KEY'] = $plainSecret
$startInfo.Environment['ALPACA_DATA_FEED'] = 'sip'
$startInfo.Environment['MSO_RUNTIME_ROOT'] = $runtimeRoot
foreach ($argument in $CollectorArguments) { [void]$startInfo.ArgumentList.Add($argument) }

try {
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($stdout.Contains($plainKeyId) -or $stdout.Contains($plainSecret) -or $stderr.Contains($plainKeyId) -or $stderr.Contains($plainSecret)) {
        throw 'Collector output rejected because credential material was detected.'
    }
    if (-not $NoLog) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $logPath = Join-Path $runtimeRoot "logs\collector-$stamp.log"
        @($stdout, $stderr) | Set-Content -LiteralPath $logPath -Encoding UTF8
    }
    if ($stdout) { Write-Output $stdout.TrimEnd() }
    if ($stderr) { Write-Error $stderr.TrimEnd() -ErrorAction Continue }
    exit $process.ExitCode
}
finally {
    $startInfo.Environment.Remove('APCA_API_KEY_ID')
    $startInfo.Environment.Remove('APCA_API_SECRET_KEY')
    $credential = $null
    $plainKeyId = $null
    $plainSecret = $null
    [GC]::Collect()
}
