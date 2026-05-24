<#
.SYNOPSIS
    Build the ModSmith Windows installer.

.DESCRIPTION
    Orchestrates the full build pipeline:
      1. Runs scripts/build_exe.ps1 to produce dist/ModSmith/modsmith.exe
      2. Runs makensis to compile the NSIS installer
      3. Verifies the output at dist/installer/ModSmithSetup.exe

.NOTES
    Prerequisites:
      - Python 3.10+ on PATH
      - PyInstaller installed: pip install pyinstaller
      - NSIS 3.x on PATH (makensis.exe)
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "$ProjectRoot\modsmith.spec")) {
    $ProjectRoot = $PSScriptRoot | Split-Path -Parent
    if (-not (Test-Path "$ProjectRoot\modsmith.spec")) {
        $ProjectRoot = Get-Location
    }
}

Push-Location $ProjectRoot
try {
    Write-Host "=== ModSmith Installer Build ===" -ForegroundColor Cyan
    Write-Host "Project root: $ProjectRoot"
    Write-Host ""

    # --- Step 1: Build the executable ---
    Write-Host "[1/3] Building executable..." -ForegroundColor Yellow
    $buildExeScript = Join-Path $ProjectRoot "scripts\build_exe.ps1"
    if (-not (Test-Path $buildExeScript)) {
        Write-Error "build_exe.ps1 not found at: $buildExeScript"
        exit 1
    }
    & powershell -ExecutionPolicy Bypass -File $buildExeScript
    if ($LASTEXITCODE -ne 0) {
        Write-Error "build_exe.ps1 failed with exit code $LASTEXITCODE"
        exit 1
    }

    # Verify the exe was produced
    $exePath = Join-Path $ProjectRoot "dist\ModSmith\modsmith.exe"
    if (-not (Test-Path $exePath)) {
        Write-Error "Expected executable not found: $exePath"
        exit 1
    }

    # --- Step 2: Ensure output directory exists ---
    $installerOutDir = Join-Path $ProjectRoot "dist\installer"
    if (-not (Test-Path $installerOutDir)) {
        New-Item -ItemType Directory -Path $installerOutDir -Force | Out-Null
    }

    # --- Step 3: Run NSIS ---
    Write-Host ""
    Write-Host "[2/3] Compiling NSIS installer..." -ForegroundColor Yellow
    $nsiFile = Join-Path $ProjectRoot "installer\ModSmithInstaller.nsi"
    if (-not (Test-Path $nsiFile)) {
        Write-Error "NSIS script not found at: $nsiFile"
        exit 1
    }

    # Check makensis is available
    $makensis = Get-Command makensis -ErrorAction SilentlyContinue
    if (-not $makensis) {
        Write-Error @"
makensis.exe not found on PATH.
Install NSIS from https://nsis.sourceforge.io/Download and add it to PATH.
"@
        exit 1
    }

    & makensis $nsiFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "makensis failed with exit code $LASTEXITCODE"
        exit 1
    }

    # --- Step 4: Verify installer output ---
    Write-Host ""
    Write-Host "[3/3] Verifying installer..." -ForegroundColor Yellow
    $installerPath = Join-Path $ProjectRoot "dist\installer\ModSmithSetup.exe"
    if (-not (Test-Path $installerPath)) {
        Write-Error "Installer not found at: $installerPath"
        exit 1
    }
    $size = (Get-Item $installerPath).Length
    Write-Host "  Found: $installerPath ($([math]::Round($size / 1MB, 2)) MB)"

    Write-Host ""
    Write-Host "=== Installer build successful! ===" -ForegroundColor Green
    Write-Host "Installer: $installerPath"
}
finally {
    Pop-Location
}
