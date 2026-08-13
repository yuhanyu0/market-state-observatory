[CmdletBinding()]
param([string]$PythonExecutable = 'python')

$ErrorActionPreference = 'Stop'
& $PythonExecutable -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable -m ruff check src tests scripts
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable -m mypy src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable scripts/validate_repo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable scripts/audit_publication.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable scripts/check_secret_patterns.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& npm test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable scripts/check_site_links.py
exit $LASTEXITCODE
