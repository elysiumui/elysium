# Build a single-file Elysium example .exe for Windows.
#
# Usage:
#     powershell -ExecutionPolicy Bypass -File scripts\build-example.ps1 butterfly
#     powershell -ExecutionPolicy Bypass -File scripts\build-example.ps1 -All
#
# Output: dist\windows\Elysium-<ExampleName>.exe
param(
    [string]$Name = "",
    [switch]$All,
    [Parameter(ValueFromRemainingArguments=$true)] $Rest
)
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

if ($All) {
    $list = & $py scripts\build.py --list
    foreach ($line in $list) {
        if ($line.StartsWith("example:")) {
            $exName = $line.Substring("example:".Length)
            Write-Host "==> Building example: $exName"
            & $py scripts\build.py example $exName @Rest
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }
    exit 0
}

if (-not $Name) {
    Write-Host "Usage: build-example.ps1 <example-folder-name> | -All" -ForegroundColor Yellow
    & $py scripts\build.py --list | Where-Object { $_ -like "example:*" }
    exit 2
}

& $py scripts\build.py example $Name @Rest
exit $LASTEXITCODE
