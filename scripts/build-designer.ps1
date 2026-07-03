# Build a single-file Elysium Designer .exe for Windows.
# Output: dist\windows\ElysiumDesigner.exe
#
# Usage (from repo root):
#     powershell -ExecutionPolicy Bypass -File scripts\build-designer.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path (Join-Path $PSScriptRoot "..")
$py = $env:PYTHON
if (-not $py) {
    if (Test-Path ".venv\Scripts\python.exe") {
        $py = ".venv\Scripts\python.exe"
    } else {
        $py = "python"
    }
}
& $py scripts\build.py designer @args
exit $LASTEXITCODE
