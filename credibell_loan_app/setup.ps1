$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 launch.py --setup }
elseif (Get-Command python -ErrorAction SilentlyContinue) { & python launch.py --setup }
else { throw 'Install Python 3.12 or 3.13, reopen VS Code, and run setup again.' }
if ($LASTEXITCODE -ne 0) { throw 'Setup did not complete. Check the error above.' }
Write-Host 'Ready. Double-click start.cmd, or run python launch.py.'
