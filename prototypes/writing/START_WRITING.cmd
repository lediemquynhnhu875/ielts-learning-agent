@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "WRITING_PORT=8766"
set "WRITING_RUNTIME=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%WRITING_RUNTIME%" (
  "%WRITING_RUNTIME%" -X utf8 app.py
) else (
  python -X utf8 app.py
)
pause
