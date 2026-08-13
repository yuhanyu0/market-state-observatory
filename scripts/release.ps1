[CmdletBinding()]
param([string]$PythonExecutable = 'python')
& (Join-Path $PSScriptRoot 'check.ps1') -PythonExecutable $PythonExecutable
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable scripts/run_synthetic_demo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable scripts/build_manifest.py
exit $LASTEXITCODE
