# Author: JY
# Starts openBIMForge Next.js dev server on the Vectorworks Web Palette port.

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
$env:OPENBIMFORGE_ROOT = $root.Path
$env:OPENBIMFORGE_RUNTIME_ROOT = Join-Path $root.Path "forge_runtime"
$env:OPENBIMFORGE_OUTPUT_ROOT = Join-Path $root.Path "forge_runtime\handoffs"
$env:OPENBIMFORGE_DEFAULT_EXECUTION_MODE = "vectorworks"
$env:TEXT2BIM_OUTPUT_ROOT = $env:OPENBIMFORGE_OUTPUT_ROOT
$env:TEXT2BIM_DEFAULT_EXECUTION_MODE = $env:OPENBIMFORGE_DEFAULT_EXECUTION_MODE
npm run dev
