<#
.SYNOPSIS
    Build modsmith.exe and modsmith_cli.exe using PyInstaller.

.DESCRIPTION
    Cleans previous build artifacts, runs PyInstaller against modsmith.spec,
    verifies both executables exist, and runs quick smoke tests.

.NOTES
    Prerequisites:
      - Python 3.10+ on PATH
      - PyInstaller installed: pip install pyinstaller
      - PySide6 installed: pip install PySide6>=6.5.0
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
    Write-Host "[1/5] Cleaning previous build artifacts..." -ForegroundColor Yellow
    foreach ($dir in @("build", "dist")) {
        $path = Join-Path $ProjectRoot $dir
        if (Test-Path $path) {
            Write-Host "  Removing $path"
            Remove-Item -Recurse -Force $path
        }
    }

    # --- Check or generate branding icon ---
    $icoPath = Join-Path $ProjectRoot "assets\modsmith.ico"
    $pngPath = Join-Path $ProjectRoot "assets\modsmith-logo.png"
    if (-not (Test-Path $icoPath)) {
        if (Test-Path $pngPath) {
            Write-Host "Branding ICO not found, but source PNG exists. Running make_icon.ps1..." -ForegroundColor Yellow
            $makeIconScript = Join-Path $ProjectRoot "scripts\make_icon.ps1"
            & powershell -ExecutionPolicy Bypass -File $makeIconScript
            if ($LASTEXITCODE -ne 0) {
                Write-Error "make_icon.ps1 failed to generate branding icon."
                exit 1
            }
        } else {
            Write-Error "Branding error: Neither assets/modsmith.ico nor assets/modsmith-logo.png exists. Official builds must be branded."
            exit 1
        }
    }

    # --- Run PyInstaller ---
    Write-Host ""
    Write-Host "[2/5] Running PyInstaller..." -ForegroundColor Yellow
    $specFile = Join-Path $ProjectRoot "modsmith.spec"
    & py -m PyInstaller $specFile --noconfirm
    if ($LASTEXITCODE -ne 0) {
        Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
        exit 1
    }

    # --- Verify GUI executable (modsmith.exe) ---
    Write-Host ""
    Write-Host "[3/5] Verifying GUI executable..." -ForegroundColor Yellow
    $guiExePath = Join-Path $ProjectRoot "dist\ModSmith\modsmith.exe"
    if (-not (Test-Path $guiExePath)) {
        Write-Error "Expected GUI executable not found at: $guiExePath"
        exit 1
    }
    $guiSize = (Get-Item $guiExePath).Length
    Write-Host "  Found GUI: $guiExePath ($([math]::Round($guiSize / 1MB, 2)) MB)"

    # --- Verify CLI executable (modsmith_cli.exe) ---
    Write-Host ""
    Write-Host "[4/5] Verifying CLI executable..." -ForegroundColor Yellow
    $cliExePath = Join-Path $ProjectRoot "dist\ModSmith\modsmith_cli.exe"
    if (-not (Test-Path $cliExePath)) {
        Write-Error "Expected CLI executable not found at: $cliExePath"
        exit 1
    }
    $cliSize = (Get-Item $cliExePath).Length
    Write-Host "  Found CLI: $cliExePath ($([math]::Round($cliSize / 1MB, 2)) MB)"

    # --- Smoke tests ---
    Write-Host ""
    Write-Host "[5/5] Smoke tests..." -ForegroundColor Yellow

    Write-Host "  CLI: modsmith_cli.exe --version"
    & $cliExePath --version
    if ($LASTEXITCODE -ne 0) {
        Write-Error "CLI smoke test failed with exit code $LASTEXITCODE"
        exit 1
    }

    Write-Host "  GUI: modsmith.exe --version"
    & $guiExePath --version
    if ($LASTEXITCODE -ne 0) {
        Write-Error "GUI smoke test failed with exit code $LASTEXITCODE"
        exit 1
    }

    Write-Host ""
    Write-Host "=== Build successful! ===" -ForegroundColor Green
    Write-Host "GUI (Windowed): $guiExePath"
    Write-Host "CLI (Console):  $cliExePath"
}
finally {
    Pop-Location
}
