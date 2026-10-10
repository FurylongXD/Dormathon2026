@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 launch.py %*
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.12 or 3.13 from python.org, then reopen this launcher.
    pause
    exit /b 1
  )
  python launch.py %*
)
if errorlevel 1 pause
