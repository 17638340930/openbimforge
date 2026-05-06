param(
    [Parameter(Mandatory = $true)]
    [string]$TaskPath,

    [string]$Model = "mimo-v2.5-pro",
    [int]$TimeoutSeconds = 900,
    [string]$ClaudeCmd = "D:\Agent\SDK\npm\node_global\claude.cmd"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$repoRootPath = $repoRoot.Path
$task = Resolve-Path $TaskPath
$reportDir = Join-Path $repoRootPath ".ai_agents\reports"
$logDir = Join-Path $repoRootPath ".ai_agents\decisions"
New-Item -ItemType Directory -Force -Path $reportDir, $logDir | Out-Null

$taskName = [IO.Path]::GetFileNameWithoutExtension($task.Path)
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $reportDir "$taskName.claude-mimo.$timestamp.md"
$stderrPath = Join-Path $logDir "$taskName.claude-mimo.$timestamp.stderr.log"

$prompt = @"
<task_context>
You are an external review agent for openBIMForge.
You must fulfill the task provided below.
Read the repository using your tools (Read, LS, Grep, etc.).
Produce a markdown report only.
Do not modify files.
</task_context>

<task_definition>
$(Get-Content -LiteralPath $task.Path -Raw)
</task_definition>
"@

Push-Location $repoRootPath
try {
    $prompt | & $ClaudeCmd `
        --print `
        --model $Model `
        --tools "Bash,Read,LS,Grep,Glob" `
        2>&1 | Set-Content -Path $reportPath -Encoding UTF8

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Claude task failed with exit code `$LASTEXITCODE."
    }

    Write-Output "REPORT=$reportPath"
}
finally {
    Pop-Location
}
