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

    # --- Step 0: Get version and architecture details ---
    $Arch = "x64"
    Write-Host "Detecting ModSmith version..." -ForegroundColor Yellow
    $Version = ""
    try {
        $Version = & py -c "import modsmith; print(modsmith.__version__)"
        $Version = $Version.Trim()
    } catch {
        try {
            $Version = & python -c "import modsmith; print(modsmith.__version__)"
            $Version = $Version.Trim()
        } catch {
            # Catch block to prevent script crash
        }
    }

    if ([string]::IsNullOrEmpty($Version)) {
        Write-Warning "Could not read version dynamically. Falling back to '1.0.0'."
        $Version = "1.0.0"
    }
    Write-Host "Detected version: $Version" -ForegroundColor Green
    Write-Host "Architecture: $Arch" -ForegroundColor Green
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

    # --- Step 2: Ensure output directory exists and clean stale setup exe ---
    $installerOutDir = Join-Path $ProjectRoot "dist\installer"
    if (-not (Test-Path $installerOutDir)) {
        New-Item -ItemType Directory -Path $installerOutDir -Force | Out-Null
    } else {
        $genericInstallerPath = Join-Path $installerOutDir "ModSmithSetup.exe"
        if (Test-Path $genericInstallerPath) {
            Write-Host "Removing stale generic installer: $genericInstallerPath"
            Remove-Item -Force $genericInstallerPath
        }
    }


    # --- Ensure branding icon exists before NSIS compilation ---
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

    # Resolve the absolute path of the icon to pass to NSIS
    $IconPath = (Resolve-Path "$ProjectRoot\assets\modsmith.ico").Path
    $IconExists = Test-Path $IconPath
    $IconSize   = if ($IconExists) { (Get-Item $IconPath).Length } else { 0 }
    Write-Host "NSIS icon path : $IconPath" -ForegroundColor Cyan
    Write-Host "Icon exists    : $IconExists"
    Write-Host "Icon size      : $([math]::Round($IconSize / 1KB, 2)) KB"

    if (-not $IconExists) {
        Write-Error "Icon file not found before NSIS compile: $IconPath"
        exit 1
    }

    # Use an arg array to avoid PowerShell quote-expansion issues with /D defines
    $MakensisArgs = @(
        "/DMODSMITH_VERSION=$Version",
        "/DMODSMITH_ICON=$IconPath",
        $nsiFile
    )
    Write-Host "Version passed to NSIS   : $Version" -ForegroundColor Cyan
    Write-Host "Icon path passed to NSIS : $IconPath" -ForegroundColor Cyan
    Write-Host "NSIS script path         : $nsiFile" -ForegroundColor Cyan
    Write-Host "makensis args  : $MakensisArgs" -ForegroundColor Cyan
    & makensis @MakensisArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "makensis failed with exit code $LASTEXITCODE"
        exit 1
    }

    # --- Step 4: Verify and rename installer output ---
    Write-Host ""
    Write-Host "[3/3] Verifying and renaming installer..." -ForegroundColor Yellow
    $genericInstallerPath = Join-Path $ProjectRoot "dist\installer\ModSmithSetup.exe"
    if (-not (Test-Path $genericInstallerPath)) {
        Write-Error "Expected generic installer not found at: $genericInstallerPath"
        exit 1
    }

    # Final named installer path
    $finalInstallerName = "modsmith_${Version}_${Arch}-setup.exe"
    $finalInstallerPath = Join-Path $ProjectRoot "dist\installer\$finalInstallerName"
    Write-Host "Final installer path     : $finalInstallerPath" -ForegroundColor Cyan

    # Remove existing named installer if it exists
    if (Test-Path $finalInstallerPath) {
        Write-Host "Removing existing named installer: $finalInstallerPath"
        Remove-Item -Force $finalInstallerPath
    }

    # Move/rename the installer
    Write-Host "Renaming generic installer to $finalInstallerName"
    Move-Item -Path $genericInstallerPath -Destination $finalInstallerPath

    # Verify both states to prevent accidental dual-uploads or missing files
    $finalExists = Test-Path $finalInstallerPath
    $genericExists = Test-Path $genericInstallerPath

    if (-not $finalExists) {
        Write-Error "Verification failed: Final named installer does not exist at: $finalInstallerPath"
        exit 1
    }

    if ($genericExists) {
        Write-Error "Verification failed: Generic installer still exists at: $genericInstallerPath"
        exit 1
    }

    $size = (Get-Item $finalInstallerPath).Length
    Write-Host "  Found final installer: $finalInstallerPath ($([math]::Round($size / 1MB, 2)) MB)"

    Write-Host ""
    Write-Host "=== Installer build successful! ===" -ForegroundColor Green
    Write-Host "Installer: $finalInstallerPath"
}
finally {
    Pop-Location
}
