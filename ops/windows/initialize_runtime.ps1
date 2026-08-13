[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$PythonExecutable
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'MarketStateObservatoryRuntime'
$children = @('secrets', 'raw', 'observations', 'data_shadow', 'model_shadow', 'logs', 'locks', 'public_staging', 'backups')
$resolvedRepository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    $adjacent = Join-Path (Split-Path -Parent $resolvedRepository) 'Python313\python.exe'
    if ($command) { $PythonExecutable = $command.Source }
    elseif (Test-Path -LiteralPath $adjacent) { $PythonExecutable = $adjacent }
    else { throw 'Python executable not found. Pass -PythonExecutable with an absolute path.' }
}
$PythonExecutable = (Resolve-Path -LiteralPath $PythonExecutable).Path

if ($PSCmdlet.ShouldProcess($runtimeRoot, 'Initialize private Market State Observatory runtime')) {
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    foreach ($name in $children) {
        New-Item -ItemType Directory -Path (Join-Path $runtimeRoot $name) -Force | Out-Null
    }
    $config = [ordered]@{
        runtime_root = $runtimeRoot
        repository_root = $resolvedRepository
        python_executable = $PythonExecutable
        mode = 'DATA_CAPTURE_ONLY'
        timezone = 'America/New_York'
        paper_positions_allowed = $false
        real_orders_allowed = $false
    }
    $configPath = Join-Path $runtimeRoot 'runtime_paths.json'
    $config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $runtimeRoot '/inheritance:r' "/grant:r" "${identity}:(OI)(CI)F" | Out-Null
    Write-Output "RUNTIME_PATH=$runtimeRoot"
    Write-Output 'RUNTIME_SECURITY=CURRENT_WINDOWS_USER_ONLY'
    Write-Output 'PAPER_POSITIONS_ALLOWED=false'
    Write-Output 'REAL_ORDERS_ALLOWED=false'
}
