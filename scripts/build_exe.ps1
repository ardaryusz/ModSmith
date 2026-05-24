<#
.SYNOPSIS
    Build modsmith.exe using PyInstaller.

.DESCRIPTION
    Cleans previous build artifacts, runs PyInstaller against modsmith.spec,
    verifies the output exists, and runs a quick smoke test.

.NOTES
    Prerequisites:
      - Python 3.10+ on PATH
      - PyInstaller installed: pip install pyinstaller
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "$ProjectRoot\modsmith.spec")) {
    # Fallback: script may be run from project root directly
    $ProjectRoot = $PSScriptRoot | Split-Path -Parent
    if (-not (Test-Path "$ProjectRoot\modsmith.spec")) {
        $ProjectRoot = Get-Location
    }
}

Push-Location $ProjectRoot
try {
    Write-Host "=== ModSmith Build Script ===" -ForegroundColor Cyan
    Write-Host "Project root: $ProjectRoot"

    # --- Clean previous artifacts ---
    Write-Host ""
    Write-Host "[1/4] Cleaning previous build artifacts..." -ForegroundColor Yellow
    foreach ($dir in @("build", "dist")) {
        $path = Join-Path $ProjectRoot $dir
        if (Test-Path $path) {
            Write-Host "  Removing $path"
            Remove-Item -Recurse -Force $path
        }
    }

    # --- Run PyInstaller ---
    Write-Host ""
    Write-Host "[2/4] Running PyInstaller..." -ForegroundColor Yellow
    $specFile = Join-Path $ProjectRoot "modsmith.spec"
    & py -m PyInstaller $specFile --noconfirm
    if ($LASTEXITCODE -ne 0) {
        Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
        exit 1
    }

    # --- Verify output ---
    Write-Host ""
    Write-Host "[3/4] Verifying output..." -ForegroundColor Yellow
    $exePath = Join-Path $ProjectRoot "dist\ModSmith\modsmith.exe"
    if (-not (Test-Path $exePath)) {
        Write-Error "Expected executable not found at: $exePath"
        exit 1
    }
    $size = (Get-Item $exePath).Length
    Write-Host "  Found: $exePath ($([math]::Round($size / 1MB, 2)) MB)"

    # --- Smoke test ---
    Write-Host ""
    Write-Host "[4/4] Smoke test: modsmith.exe --version" -ForegroundColor Yellow
    & $exePath --version
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Smoke test failed with exit code $LASTEXITCODE"
        exit 1
    }

    Write-Host ""
    Write-Host "=== Build successful! ===" -ForegroundColor Green
    Write-Host "Executable: $exePath"
}
finally {
    Pop-Location
}
