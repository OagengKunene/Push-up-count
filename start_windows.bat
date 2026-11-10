@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 setup_and_run.py %*
) else (
    python setup_and_run.py %*
)
set "PUSHUP_EXIT=%errorlevel%"
if not "%PUSHUP_EXIT%"=="0" (
    echo.
    echo The program could not start. Read the error above and README.md.
    pause
)
exit /b %PUSHUP_EXIT%
