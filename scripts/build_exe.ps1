<#
.SYNOPSIS
    Build modsmith.exe and modsmith_cli.exe using PyInstaller.

.DESCRIPTION
    Cleans previous build artifacts, runs PyInstaller against modsmith.spec,
    verifies both executables exist, and runs quick smoke tests.

    Cleanup is hardened against Windows file locks:
      - Any packaged ModSmith processes whose path is under dist/ are stopped first.
      - Removal retries up to 5 times (1 s sleep) before failing clearly.

    The windowed GUI smoke test (modsmith.exe --version) is run with a 10-second
    timeout; the process is killed if it does not exit in time.

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

# ---------------------------------------------------------------------------
# Helper: stop any packaged ModSmith processes whose executable lives under
# the project dist directory.  Avoids killing unrelated system processes.
# ---------------------------------------------------------------------------
function Stop-ModSmithProcesses {
    param([string]$DistRoot)

    $names = @("modsmith", "modsmith_cli")
    foreach ($name in $names) {
        $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
        foreach ($proc in $procs) {
            $procPath = ""
            try { $procPath = $proc.Path } catch { }
            if ($procPath -and $procPath.StartsWith($DistRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                Write-Host "  Stopping locked process: $name (PID $($proc.Id)) at $procPath" -ForegroundColor Yellow
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }
    # Give the OS a moment to release file handles
    Start-Sleep -Milliseconds 500
}

# ---------------------------------------------------------------------------
# Helper: remove a directory with up to $MaxTries retries on lock errors.
# ---------------------------------------------------------------------------
function Remove-WithRetry {
    param(
        [string]$Path,
        [int]$MaxTries = 5,
        [int]$SleepSec = 1
    )

    for ($i = 1; $i -le $MaxTries; $i++) {
        try {
            Remove-Item -Recurse -Force $Path -ErrorAction Stop
            return  # success
        } catch {
            if ($i -lt $MaxTries) {
                Write-Host "  Removal attempt $i/$MaxTries failed (locked?), retrying in ${SleepSec}s..." -ForegroundColor Yellow
                [GC]::Collect()
                [GC]::WaitForPendingFinalizers()
                Start-Sleep -Seconds $SleepSec
            } else {
                Write-Host ""
                Write-Host "ERROR: Could not clean '$Path' because files are still locked." -ForegroundColor Red
                Write-Host "  Close ModSmith GUI and any terminals using dist/, then retry." -ForegroundColor Red
                Write-Host "  Last error: $($_.Exception.Message)" -ForegroundColor Red
                throw  # re-throw so $ErrorActionPreference = Stop propagates
            }
        }
    }
}

Push-Location $ProjectRoot
try {
    Write-Host "=== ModSmith Build Script ===" -ForegroundColor Cyan
    Write-Host "Project root: $ProjectRoot"

    # --- Kill any running ModSmith dist processes before cleaning ---
    $distRoot = Join-Path $ProjectRoot "dist\ModSmith"
    if (Test-Path $distRoot) {
        Write-Host ""
        Write-Host "[0/5] Stopping any running ModSmith dist processes..." -ForegroundColor Yellow
        Stop-ModSmithProcesses -DistRoot $distRoot
    }

    # --- Clean previous artifacts (with retry) ---
    Write-Host ""
    Write-Host "[1/5] Cleaning previous build artifacts..." -ForegroundColor Yellow
    foreach ($dir in @("build", "dist")) {
        $path = Join-Path $ProjectRoot $dir
        if (Test-Path $path) {
            Write-Host "  Removing $path"
            Remove-WithRetry -Path $path
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

    # CLI smoke test - console exe, straightforward
    Write-Host "  CLI: modsmith_cli.exe --version"
    & $cliExePath --version
    if ($LASTEXITCODE -ne 0) {
        Write-Error "CLI smoke test failed with exit code $LASTEXITCODE"
        exit 1
    }

    # GUI smoke test - windowed exe (console=False); must not stay resident.
    # Run via Start-Process with a 10-second timeout; kill if it hangs.
    Write-Host "  GUI: modsmith.exe --version (timeout 10s)"
    $guiStartArgs = @{
        FilePath     = $guiExePath
        ArgumentList = "--version"
        PassThru     = $true
        WindowStyle  = "Hidden"
        ErrorAction  = "Stop"
    }
    $guiJob = Start-Process @guiStartArgs
    $exited = $guiJob.WaitForExit(10000)
    if (-not $exited) {
        Write-Host "  GUI process did not exit within 10 seconds - killing it." -ForegroundColor Yellow
        Stop-Process -Id $guiJob.Id -Force -ErrorAction SilentlyContinue
        Write-Error "GUI smoke test timed out (modsmith.exe --version did not exit within 10s)"
        exit 1
    }
    if ($guiJob.ExitCode -ne 0) {
        Write-Error "GUI smoke test failed: modsmith.exe --version exited with code $($guiJob.ExitCode)"
        exit 1
    }
    Write-Host "  GUI process exited cleanly (exit code 0)"

    Write-Host ""
    Write-Host "=== Build successful! ===" -ForegroundColor Green
    Write-Host "GUI (Windowed): $guiExePath"
    Write-Host "CLI (Console):  $cliExePath"
}
finally {
    Pop-Location
}
