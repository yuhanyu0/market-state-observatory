[CmdletBinding()]
param([string]$PythonExecutable)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $adjacent = Join-Path (Split-Path -Parent $root) 'Python313\python.exe'
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) { $PythonExecutable = $command.Source }
    elseif (Test-Path -LiteralPath $adjacent) { $PythonExecutable = $adjacent }
    else { throw 'Python not found. Pass -PythonExecutable.' }
}
& $PythonExecutable -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& npm ci
exit $LASTEXITCODE
