# openBIMForge Vectorworks Plugin Installer
# Run this script to install the Web Palette plugin for Vectorworks 2024.

param(
    [string]$VectorworksYear = "2024"
)

$ErrorActionPreference = "Stop"

# Get openBIMForge root directory
$OpenBimForgeRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PluginSource = Join-Path $OpenBimForgeRoot "vectorworks_plugin\openBIMForge2024"

# Vectorworks Plug-ins directory
$VwPlugIns = Join-Path $env:APPDATA "Nemetschek\Vectorworks\$VectorworksYear\Plug-ins"

# Check if source exists
if (-not (Test-Path $PluginSource)) {
    Write-Host "ERROR: Plugin source not found: $PluginSource" -ForegroundColor Red
    exit 1
}

# Create Plug-ins directory if needed
if (-not (Test-Path $VwPlugIns)) {
    Write-Host "ERROR: Vectorworks Plug-ins directory not found: $VwPlugIns" -ForegroundColor Red
    Write-Host "Please install Vectorworks $VectorworksYear first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Installing openBIMForge Vectorworks plugin..." -ForegroundColor Cyan
Write-Host "  Source: $PluginSource"
Write-Host "  Target: $VwPlugIns"
Write-Host ""

# Method 1: Create shortcut (recommended - keeps files in project folder)
$ShortcutPath = Join-Path $VwPlugIns "openBIMForge2024 - shortcut.lnk"

Write-Host "Creating shortcut..." -ForegroundColor Yellow
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PluginSource
$Shortcut.WorkingDirectory = $PluginSource
$Shortcut.Description = "openBIMForge BIM Automation Plugin"
$Shortcut.Save()

Write-Host "  Created: $ShortcutPath" -ForegroundColor Green
Write-Host ""

# Install Python paths
Write-Host "Installing Python paths..." -ForegroundColor Yellow
$PythonExternals = Join-Path $env:APPDATA "Nemetschek\Vectorworks\$VectorworksYear\Python Externals"
New-Item -ItemType Directory -Force -Path $PythonExternals | Out-Null

$PthPath = Join-Path $PythonExternals "openbimforge.pth"
$Lines = @(
    $OpenBimForgeRoot,
    (Join-Path $OpenBimForgeRoot "forge_core")
)
[System.IO.File]::WriteAllLines($PthPath, $Lines, [System.Text.UTF8Encoding]::new($false))

Write-Host "  Created: $PthPath" -ForegroundColor Green
Write-Host "  Contents:" -ForegroundColor Gray
Get-Content -LiteralPath $PthPath | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
Write-Host ""

# Summary
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Restart Vectorworks $VectorworksYear" -ForegroundColor White
Write-Host "  2. Open: Window > Palettes > Web Palettes > openBIMForge" -ForegroundColor White
Write-Host "  3. The plugin will load from: $PluginSource" -ForegroundColor White
Write-Host ""
Write-Host "Note: The shortcut points to the project folder." -ForegroundColor Yellow
Write-Host "      If you move the openBIMForge folder, run this installer again." -ForegroundColor Yellow
