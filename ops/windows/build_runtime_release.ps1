[CmdletBinding(SupportsShouldProcess)]
param([string]$PythonExecutable = 'python')

$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ((& git -C $repository status --porcelain).Count -gt 0) {
    throw 'A production release must be built from a clean committed working tree.'
}
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$configPath = Join-Path $runtimeRoot 'runtime_paths.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    & (Join-Path $PSScriptRoot 'initialize_runtime.ps1') -PythonExecutable $PythonExecutable
}
$pythonCommand = Get-Command $PythonExecutable -ErrorAction SilentlyContinue
if ($pythonCommand) { $PythonExecutable = $pythonCommand.Source }
$PythonExecutable = (Resolve-Path -LiteralPath $PythonExecutable).Path
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
    New-Item -ItemType Directory -Path $staging,(Join-Path $staging 'wheel'),(Join-Path $staging 'config'),(Join-Path $staging 'schemas'),(Join-Path $staging 'frozen') | Out-Null
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
    $universe = Get-Content (Join-Path $staging 'frozen\runtime_universe_v1.json') -Raw | ConvertFrom-Json
    [ordered]@{
        schema_version = 'mso-frozen-membership-v1'; source = 'runtime_universe_v1'
        effective_start = $universe.frozen_at_utc; themes = $universe.themes
    } | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $staging 'frozen\membership_snapshot_v1.json') -Encoding utf8
    [ordered]@{
        schema_version = 'mso-runtime-release-config-v1'; queue_size = 10000
        stream_disk_budget_bytes = 2147483648; full_stream_debug = $false
        cross_section_skew_limit_seconds = 5; paper_positions_allowed = $false
        real_orders_allowed = $false
    } | ConvertTo-Json | Set-Content (Join-Path $staging 'config\runtime_release_config.json') -Encoding utf8
    & $releasePython -m market_state_observatory.runtime.release_identity `
        --build-manifest --release $staging --repository $repository --git-sha $gitSha `
        --release-version $version --output (Join-Path $staging 'release_manifest.json')
    if ($LASTEXITCODE -ne 0) { throw 'Release manifest generation failed.' }
    $manifest = Get-Content (Join-Path $staging 'release_manifest.json') -Raw | ConvertFrom-Json
    $wheelHash = $manifest.wheel_sha256
    if ($PSCmdlet.ShouldProcess($releaseRoot, 'Freeze production wheel and dedicated venv')) {
        Move-Item -LiteralPath $staging -Destination $releaseRoot
        $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        $config | Add-Member -Force NoteProperty release_root $releaseRoot
        $config | Add-Member -Force NoteProperty release_python (Join-Path $releaseRoot 'venv\Scripts\python.exe')
        $config | Add-Member -Force NoteProperty release_launcher (Join-Path $releaseRoot 'runtime_release_launcher.ps1')
        $config | Add-Member -Force NoteProperty release_version $version
        $config | Add-Member -Force NoteProperty release_experiment_lane $manifest.experiment_lane
        $config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding utf8
        Write-Output "RELEASE_ROOT=$releaseRoot"
        Write-Output "RELEASE_VERSION=$version"
        Write-Output "WHEEL_SHA256=$wheelHash"
        Write-Output "EXPERIMENT_LANE=$($manifest.experiment_lane)"
        Write-Output 'FORMAL_DATA_SHADOW_STARTED=false'
    }
}
catch {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    throw
}
