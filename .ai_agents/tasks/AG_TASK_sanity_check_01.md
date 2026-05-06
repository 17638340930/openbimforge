# Antigravity Task Request

> **Attention Antigravity / Gemini Agent**: You are receiving this prompt via manual user trigger as part of the openBIMForge "Markdown Bridge Workflow". You act as an external consulting expert to Codex. Please execute the following analysis strictly adhering to the constraints below.

## 1. Task Metadata
- **Task Name**: AG_TASK_sanity_check_01
- **Recommended Model**: gemini-3.1-flash
- **Task Class**: Sanity Check
- **Project Root**: D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge
- **Task File**: .ai_agents/tasks/AG_TASK_sanity_check_01.md
- **Target Report Path**: .ai_agents/reports/AG_REPORT_sanity_check_01.md

## 2. Strict Constraints (CRITICAL)
1. **READ-ONLY BUSINESS CODE**: You must **NOT** use your writing tools to modify any files inside `app/`, `components/`, `forge_core/`, `lib/`, `public/`, or `package.json`.
2. **RESTRICTED WRITE ACCESS**: You are only allowed to create or update files inside the `.ai_agents/` directory, specifically the target report path: `.ai_agents/reports/AG_REPORT_sanity_check_01.md`.
3. **NO SECRETS**: Do not include any API keys, tokens, passwords, credentials, or encrypted secrets in your responses or generated report.
4. **ADVISORY ROLE ONLY**: Do not execute disruptive commands that modify the project structure. If cleanup or dependency changes are recommended, provide them as advisory notes in the markdown report only. Codex will review and decide whether to apply anything.

## 3. Task Body / Context
Quickly scan the openBIMForge project for obvious stale or redundant package/static-asset surface area.

Scope:
- Read `package.json`.
- Inspect the `public/` directory at a practical top-level and near-top-level depth.
- If useful, search for references to suspicious public assets in the codebase, but keep this as a fast sanity check rather than a deep audit.

Check for:
- Dependencies or scripts in `package.json` that look obviously outdated, duplicated, unused, suspicious, or inconsistent with the project shape.
- Static files in `public/` that look obviously redundant, obsolete, duplicated, placeholder-only, generated cache artifacts, or likely unused.
- Any quick wins worth sending back to Codex for follow-up.

Do not modify files.

## 4. Expected Output Format
Save a structured markdown report to:

```text
.ai_agents/reports/AG_REPORT_sanity_check_01.md
```

The report must use this structure:

```md
# Antigravity Sanity Check Report 01

## Model Used
- Recommended: gemini-3.1-flash
- Actual: <state the model you used, if known>

## Executive Summary
<2-5 concise bullets>

## Scope Checked
- package.json
- public/
- Any reference searches performed

## Findings
| Severity | Area | Finding | Evidence | Recommendation |
|---|---|---|---|---|

Use severity values:
- High: likely harmful or clearly wrong
- Medium: plausible cleanup or maintenance risk
- Low: minor redundancy, naming, or follow-up candidate
- Info: useful context but no action needed

## Evidence Paths
List concrete file paths checked or referenced.

## Confidence
State confidence and limits of this quick scan.

## Suggested Next Step for Codex
Give Codex a short, concrete next action list.
```

## Instructions for Antigravity
1. Please read the necessary context using your file/search tools.
2. Conduct the required analysis based on the `Task Body`.
3. Generate the structured markdown report according to `Expected Output Format`.
4. Save the final report to the exact path specified in `Target Report Path`.
5. If Antigravity cannot write the file directly, output the complete markdown report in chat so the user can save it to `.ai_agents/reports/AG_REPORT_sanity_check_01.md`.
6. Once completed, provide a very brief summary message indicating whether the report file was successfully written.
