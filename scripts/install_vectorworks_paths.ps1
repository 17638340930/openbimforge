# Author: JY
# Installs openBIMForge Python import paths for Vectorworks 2024.
# Run this from PowerShell after cloning/moving the openBIMForge folder.

param(
    [string]$VectorworksYear = "2024",
    [string]$OpenBimForgeRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$pythonExternals = Join-Path $env:APPDATA "Nemetschek\Vectorworks\$VectorworksYear\Python Externals"
New-Item -ItemType Directory -Force -Path $pythonExternals | Out-Null

$root = (Resolve-Path $OpenBimForgeRoot).Path
$pthPath = Join-Path $pythonExternals "openbimforge.pth"
$lines = @(
    $root,
    (Join-Path $root "forge_core")
)

[System.IO.File]::WriteAllLines($pthPath, $lines, [System.Text.UTF8Encoding]::new($false))

Write-Host "openBIMForge Vectorworks Python paths installed:" -ForegroundColor Green
Write-Host "  $pthPath"
Write-Host "Contents:"
Get-Content -LiteralPath $pthPath | ForEach-Object { Write-Host "  $_" }
Write-Host "Restart Vectorworks after running this script." -ForegroundColor Yellow
