[CmdletBinding()]
param(
    [ValidateSet('rehearsal', 'formal')][string]$Mode = 'formal',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Runtime is not initialized.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$arguments = @('-m', 'market_state_observatory.runtime.daily_daemon', '--mode', $Mode)
if ($DryRun) {
    $env:MSO_RUNTIME_ROOT = $runtimeRoot
    try {
        & $config.python_executable @arguments '--dry-run'
        exit $LASTEXITCODE
    }
    finally { Remove-Item Env:MSO_RUNTIME_ROOT -ErrorAction SilentlyContinue }
}

$invoke = Join-Path $PSScriptRoot 'invoke_collector_with_credentials.ps1'
& $invoke -CollectorArguments $arguments
$exitCode = $LASTEXITCODE
$failureStage = 'collector'
if ($exitCode -eq 0 -and $Mode -eq 'formal') {
    $failureStage = 'publication'
    $etNow = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
        [DateTime]::UtcNow,
        'Eastern Standard Time'
    )
    $dayRoot = Join-Path $runtimeRoot "data_shadow\$($etNow.ToString('yyyy-MM-dd'))"
    $quality = if (Test-Path -LiteralPath $dayRoot -PathType Container) {
        Get-ChildItem -LiteralPath $dayRoot -Filter 'DATA_QUALITY.json' -File -Recurse |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
    }
    $publicationLog = Join-Path $runtimeRoot "logs\publication-$($etNow.ToString('yyyyMMdd-HHmmss')).log"
    if (-not $quality) {
        @('PUBLICATION_STATUS=FAIL', 'FAILURE_REASON=QUALITY_ARTIFACT_MISSING') |
            Set-Content -LiteralPath $publicationLog -Encoding UTF8
        $exitCode = 1
    }
    else {
        try {
            $publisher = Join-Path $PSScriptRoot 'publish_public_snapshot.ps1'
            $publicationOutput = & $publisher -PrivateQualityPath $quality.FullName -Push 2>&1
            $exitCode = $LASTEXITCODE
            $publicationOutput | Set-Content -LiteralPath $publicationLog -Encoding UTF8
        }
        catch {
            @(
                'PUBLICATION_STATUS=FAIL',
                "ERROR_TYPE=$($_.Exception.GetType().Name)",
                'CREDENTIAL_VALUES_LOGGED=false'
            ) | Set-Content -LiteralPath $publicationLog -Encoding UTF8
            $exitCode = 1
        }
    }
}
if ($exitCode -ne 0) {
    $alert = [ordered]@{
        status = 'RUNTIME_HEALTH_ALERT'
        exit_code = $exitCode
        failure_stage = $failureStage
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        credential_values_logged = $false
        paper_positions = 0
        real_orders = 0
    }
    $alertPath = Join-Path $runtimeRoot "logs\health-alert-$([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')).json"
    $alert | ConvertTo-Json | Set-Content -LiteralPath $alertPath -Encoding UTF8
}
exit $exitCode
