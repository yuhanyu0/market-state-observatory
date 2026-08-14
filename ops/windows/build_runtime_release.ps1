[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$PythonExecutable = 'python',
    [switch]$ActivateRuntime
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\process_compat.ps1')
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (@(& git -C $repository status --porcelain).Count -gt 0) {
    throw 'A production release must be built from a clean committed working tree.'
}
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    & (Join-Path $PSScriptRoot 'initialize_runtime.ps1') -PythonExecutable $PythonExecutable
}
$PythonExecutable = Resolve-MsoBootstrapPython -Candidate $PythonExecutable
$pyproject = Get-Content -LiteralPath (Join-Path $repository 'pyproject.toml') -Raw
$version = [regex]::Match($pyproject, '(?m)^version = "([^"]+)"$').Groups[1].Value
if (-not $version) { throw 'Project version could not be resolved.' }
$gitSha = (& git -C $repository rev-parse HEAD).Trim()
$releaseId = "v$version-$($gitSha.Substring(0,8))"
$releaseRoot = Join-Path $runtimeRoot "releases\$releaseId"
$staging = Join-Path $runtimeRoot "releases\.staging-$releaseId"
if (Test-Path -LiteralPath $releaseRoot) { throw "Immutable release already exists: $releaseRoot" }
if (Test-Path -LiteralPath $staging) { throw "Stale release staging exists: $staging" }

try {
    New-Item -ItemType Directory -Path $staging,(Join-Path $staging 'wheel'),(Join-Path $staging 'config'),(Join-Path $staging 'schemas'),(Join-Path $staging 'frozen'),(Join-Path $staging 'lib') | Out-Null
    & $PythonExecutable -m build --wheel --outdir (Join-Path $staging 'wheel') $repository
    if ($LASTEXITCODE -ne 0) { throw 'Wheel build failed.' }
    $wheels = @(Get-ChildItem (Join-Path $staging 'wheel') -Filter *.whl -File)
    if ($wheels.Count -ne 1) { throw "Expected one wheel, found $($wheels.Count)." }
    $wheel = $wheels[0]
    & $PythonExecutable -m venv (Join-Path $staging 'venv')
    $releasePython = Join-Path $staging 'venv\Scripts\python.exe'
    & $releasePython -m pip install --disable-pip-version-check $wheel.FullName
    if ($LASTEXITCODE -ne 0) { throw 'Frozen venv installation failed.' }
    (& $releasePython -m pip freeze | Sort-Object) | Set-Content -LiteralPath (Join-Path $staging 'dependency.lock') -Encoding ascii
    Copy-Item (Join-Path $repository 'config\runtime_universe_v1.json') (Join-Path $staging 'frozen\runtime_universe_v1.json')
    Copy-Item (Join-Path $repository 'config\publication_policy.yml') (Join-Path $staging 'config\publication_policy.yml')
    Copy-Item (Join-Path $repository 'schemas\*.json') (Join-Path $staging 'schemas')
    Copy-Item (Join-Path $PSScriptRoot 'runtime_release_launcher.ps1') (Join-Path $staging 'runtime_release_launcher.ps1')
    Copy-Item (Join-Path $PSScriptRoot 'lib\process_compat.ps1') (Join-Path $staging 'lib\process_compat.ps1')
    Copy-Item (Join-Path $PSScriptRoot 'lib\scheduler_safety.ps1') (Join-Path $staging 'lib\scheduler_safety.ps1')
    $universe = Get-Content (Join-Path $staging 'frozen\runtime_universe_v1.json') -Raw | ConvertFrom-Json
    [ordered]@{
        schema_version = 'mso-frozen-membership-v1'; source = 'runtime_universe_v1'
        effective_start = $universe.frozen_at_utc; themes = $universe.themes
    } | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $staging 'frozen\membership_snapshot_v1.json') -Encoding utf8
    [ordered]@{
        schema_version = 'mso-runtime-release-config-v4'; queue_size = 10000
        stream_disk_budget_bytes = 2147483648; full_stream_debug = $false
        stream_checkpoint_message_interval = 10000; stream_checkpoint_seconds = 10
        freeze_duration_limit_seconds = 5
        event_time_dispersion_diagnostic_only = $true
        pit_primary_source = 'websocket_sip'
        rest_role = 'backup_reconciliation_and_derived_features_only'
        paper_positions_allowed = $false
        real_orders_allowed = $false
        minimum_windows_powershell_version = '5.1'
        process_compat_version = '0.4.3'
        scheduler_default_mode = 'rehearsal'
        formal_promotion_required = $true
        minimum_scheduler_rehearsal_sessions = 3
    } | ConvertTo-Json | Set-Content (Join-Path $staging 'config\runtime_release_config.json') -Encoding utf8
    $testedShells = @("$($PSVersionTable.PSEdition) $($PSVersionTable.PSVersion.ToString())")
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwsh) {
        $pwshIdentity = (& $pwsh.Source -NoProfile -Command '$PSVersionTable.PSEdition + " " + $PSVersionTable.PSVersion.ToString()').Trim()
        if ($pwshIdentity) { $testedShells += $pwshIdentity }
    }
    $manifestArguments = @(
        '-I', '-m', 'market_state_observatory.runtime.release_identity',
        '--build-manifest', '--release', $staging, '--repository', $repository,
        '--git-sha', $gitSha, '--release-version', $version,
        '--output', (Join-Path $staging 'release_manifest.json')
    )
    foreach ($shell in $testedShells) { $manifestArguments += @('--tested-shell', $shell) }
    & $releasePython @manifestArguments
    if ($LASTEXITCODE -ne 0) { throw 'Release manifest generation failed.' }
    $manifest = Get-Content (Join-Path $staging 'release_manifest.json') -Raw | ConvertFrom-Json
    $wheelHash = $manifest.wheel_sha256
    if ($PSCmdlet.ShouldProcess($releaseRoot, 'Freeze production wheel and dedicated venv')) {
        Move-Item -LiteralPath $staging -Destination $releaseRoot
        if ($ActivateRuntime) {
            & (Join-Path $PSScriptRoot 'select_runtime_release.ps1') `
                -ReleaseRoot $releaseRoot -Select
            if ($LASTEXITCODE -ne 0) { throw 'Frozen release selection failed.' }
        }
        Write-Output "RELEASE_ROOT=$releaseRoot"
        Write-Output "RELEASE_VERSION=$version"
        Write-Output "WHEEL_SHA256=$wheelHash"
        Write-Output "EXPERIMENT_LANE=$($manifest.experiment_lane)"
        Write-Output "RUNTIME_CONFIG_ACTIVATED=$($ActivateRuntime.ToString().ToLowerInvariant())"
        Write-Output 'SCHEDULER_CHANGED=false'
        Write-Output 'FORMAL_DATA_SHADOW_STARTED=false'
    }
}
catch {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    throw
}
