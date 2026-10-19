@echo off
chcp 65001 >nul
pushd "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; if(Test-Path -LiteralPath $p){ & $p -X utf8 cases/run_user_map_case.py --gui } elseif(Get-Command py -ErrorAction SilentlyContinue){ & py -3 -X utf8 cases/run_user_map_case.py --gui } else { & python -X utf8 cases/run_user_map_case.py --gui }; exit $LASTEXITCODE"
if errorlevel 1 pause
popd
