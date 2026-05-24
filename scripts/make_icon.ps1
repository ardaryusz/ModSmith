<#
.SYNOPSIS
    Generate the ModSmith ICO icon file from the real source logo PNG.

.DESCRIPTION
    Reads assets/modsmith-logo.png (the real project logo -- never generated
    or redrawn by this script) and writes assets/modsmith.ico containing
    sizes 16, 24, 32, 48, 64, 128, 256.

    Also writes human-readable preview PNGs to assets/icon-preview/ so the
    result can be inspected visually. Previews reflect the real logo as-is
    and are listed in .gitignore.

    This script never generates, redraws, recolors, or simplifies the logo.

.NOTES
    Prerequisites:
      - Python 3.10+ on PATH
      - Pillow installed: py -m pip install Pillow
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Locate project root
# ---------------------------------------------------------------------------
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$ProjectRoot\modsmith.spec")) {
    $ProjectRoot = $PSScriptRoot | Split-Path -Parent
    if (-not (Test-Path "$ProjectRoot\modsmith.spec")) {
        $ProjectRoot = Get-Location
    }
}

$AssetsDir  = Join-Path $ProjectRoot "assets"
$PngPath    = Join-Path $AssetsDir "modsmith-logo.png"
$IcoPath    = Join-Path $AssetsDir "modsmith.ico"
$PreviewDir = Join-Path $AssetsDir "icon-preview"

# ---------------------------------------------------------------------------
# Guard: the real logo must already exist -- we never create it here
# ---------------------------------------------------------------------------
if (-not (Test-Path $PngPath)) {
    Write-Error "Source logo not found: $PngPath`nPlace your PNG there and re-run this script."
    exit 1
}

# ---------------------------------------------------------------------------
# Check Pillow
# ---------------------------------------------------------------------------
$PythonCmd = "py"
$HasPillow = & py -c "import PIL; print('OK')" 2>$null
if ($HasPillow -ne "OK") {
    $HasPillow = & python -c "import PIL; print('OK')" 2>$null
    if ($HasPillow -eq "OK") {
        $PythonCmd = "python"
    } else {
        Write-Error "Pillow not installed. Run: py -m pip install Pillow"
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Clean outputs
# ---------------------------------------------------------------------------
if (Test-Path $IcoPath) {
    Write-Host "Removing old ICO: $IcoPath"
    Remove-Item -Force $IcoPath
}
if (Test-Path $PreviewDir) {
    Remove-Item -Recurse -Force $PreviewDir
}
New-Item -ItemType Directory -Path $PreviewDir -Force | Out-Null

Write-Host "Generating $IcoPath from $PngPath ..." -ForegroundColor Yellow

# ---------------------------------------------------------------------------
# Python: generate ICO + preview PNGs from the real logo
# ---------------------------------------------------------------------------
& $PythonCmd -c @"
import sys, os
from PIL import Image

png_path    = r'$PngPath'
ico_path    = r'$IcoPath'
preview_dir = r'$PreviewDir'

try:
    src = Image.open(png_path)

    # Flatten to RGB on black only if the source has an alpha channel,
    # so ICO frames are palette-clean for Windows. No other modification.
    if src.mode in ('RGBA', 'LA') or (src.mode == 'P' and 'transparency' in src.info):
        bg = Image.new('RGB', src.size, (0, 0, 0))
        converted = src.convert('RGBA')
        bg.paste(converted, mask=converted.split()[3])
        src = bg
    else:
        src = src.convert('RGB')

    target_sizes = [16, 24, 32, 48, 64, 128, 256]

    # Write preview PNGs from the real logo at each size (unmodified orientation)
    for sz in target_sizes:
        frame = src.resize((sz, sz), Image.Resampling.LANCZOS)
        preview_path = os.path.join(preview_dir, f'icon_{sz}x{sz}.png')
        frame.save(preview_path, format='PNG')

    # Save ICO using Pillow's native multi-size support.
    # No manual frame assembly, no vertical flip.
    ico_sizes = [(sz, sz) for sz in target_sizes]
    src.save(ico_path, format='ICO', sizes=ico_sizes)

    print('Sizes  : ' + str(target_sizes))
    print('ICO    : ' + ico_path)
    print('Preview: ' + preview_dir)

except Exception as exc:
    print(f'ERROR: {exc}', file=sys.stderr)
    sys.exit(1)
"@

if ($LASTEXITCODE -ne 0) {
    Write-Error "ICO generation failed."
    exit 1
}

if (-not (Test-Path $IcoPath)) {
    Write-Error "ICO file not created at: $IcoPath"
    exit 1
}

$icoSize = (Get-Item $IcoPath).Length
Write-Host ""
Write-Host "Success! $IcoPath ($([math]::Round($icoSize / 1KB, 2)) KB)" -ForegroundColor Green
Write-Host ""
Write-Host "Previews:" -ForegroundColor Cyan
Get-ChildItem $PreviewDir | ForEach-Object { Write-Host "  $($_.FullName)" }