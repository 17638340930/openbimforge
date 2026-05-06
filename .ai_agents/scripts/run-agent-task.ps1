param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("claude", "opencode", "gemini", "antigravity")]
    [string]$Provider,

    [Parameter(Mandatory = $true)]
    [string]$TaskFile,

    [string]$ProjectRoot,
    [string]$OutDir,
    [string]$Model,
    [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $ProjectRoot) { $ProjectRoot = $repoRoot.Path }
if (-not $OutDir) { $OutDir = Join-Path $repoRoot.Path ".ai_agents\reports" }

$router = "D:\Agent\agent-router\scripts\run-agent-task.ps1"
if (-not (Test-Path -LiteralPath $router)) {
    throw "Global agent router was not found: $router"
}

& $router -Provider $Provider -TaskFile $TaskFile -ProjectRoot $ProjectRoot -OutDir $OutDir -Model $Model -TimeoutSec $TimeoutSec
