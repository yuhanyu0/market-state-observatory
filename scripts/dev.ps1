[CmdletBinding()]
param()
& npm run dev -- --host 127.0.0.1
exit $LASTEXITCODE
