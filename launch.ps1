param([ValidateSet('gui','single','batch','safety')][string]$Mode = 'gui')
$ErrorActionPreference = 'Stop'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
Push-Location -LiteralPath $PSScriptRoot
try {
    if (Test-Path -LiteralPath $bundledPython) {
        & $bundledPython -X utf8 run.py --mode $Mode
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -X utf8 run.py --mode $Mode
    } else {
        & python -X utf8 run.py --mode $Mode
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
