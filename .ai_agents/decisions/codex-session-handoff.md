# Codex Session Handoff

## Current Project

`D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge`

## Current Working State

The Nexus BIM full chain is working:

1. Chat triggers Nexus orchestration.
2. Stage 1 Architect and Stage 2 Constructor complete.
3. Stage 3 writes `nexus_payload_session-...json`.
4. Vectorworks Web Palette/VM receives exact `payloadPath`.
5. VM creates VWX/IFC and writes `.result.json`.
6. Frontend reads `.result.json` and shows completed status.

## Important Fixes Already Applied

### VM trigger / stale payload fix

Files:

- `forge_core/build_agent/vectorworks_watch_runner.py`
- `vectorworks_plugin/openBIMForge2024/tool_agent/vs_interface.py`
- `C:\Users\92586\AppData\Roaming\Nemetschek\Vectorworks\2024\Plug-ins\tool_agent\vs_interface.py`

Changes:

- Runner now scans newest payloads first.
- Runner skips `.failed` payloads.
- Palette initialization without exact `payloadPath` no longer scans and executes old payloads.
- Actual Vectorworks user plugin shim was patched too.

### Frontend execution card cleanup

File:

- `components/chat-message-display.tsx`

Changes:

- Removed useless `下载 VWX` / `下载 IFC` buttons from the execution card.
- When `.result.json` is read successfully, Stage 4 display is overwritten from `waiting/polling` to `completed`.
- Stale final text saying “payload delivered, waiting for VM” is filtered after success.

Validation previously passed:

- `npx biome lint components/chat-message-display.tsx`
- `npx tsc --noEmit --pretty false`

## External Agent / CLI Investigation

Goal:

Use cheaper local agents to create scan reports while Codex remains the final implementer.

Findings:

- Claude Code CLI is installed globally at:
  `D:\Agent\SDK\npm\node_global\claude.cmd`
- The PATH also contains a broken Claude install:
  `D:\Agent\claude-code\node_modules\.bin\claude.ps1`
- Use the global `.cmd` path explicitly.
- Claude is configured through Mimo-compatible Anthropic env vars in:
  `C:\Users\92586\.claude\settings.json`
  and Codex config.
- Antigravity CLI exists:
  `D:\devloop\Google IDE\Antigravity\bin\antigravity.cmd`
  but it is VSCode-like: can open windows/list extensions, no confirmed headless prompt API.
- Gemini/Antigravity stores prior reports under:
  `C:\Users\92586\.gemini\antigravity\brain\...`
  but no direct prompt CLI was found.

## New External Agent Queue

Created:

- `.ai_agents/AGENT_WORKFLOW.md`
- `.ai_agents/scripts/run-claude-task.ps1`
- `.ai_agents/tasks/asset-doc-cleanup-audit.md`
- `.ai_agents/tasks/code-redundancy-review.md`
- `.ai_agents/tasks/docs-rewrite-plan.md`
- `.ai_agents/tasks/smoke-test.md`

Intended workflow:

1. Codex writes tasks into `.ai_agents/tasks/`.
2. Claude/Gemini/Mimo produce markdown reports into `.ai_agents/reports/`.
3. Codex reviews reports and applies only verified changes.

Status:

- The queue structure is created.
- `run-claude-task.ps1` still needs final verification. The last smoke run was interrupted and produced an empty report.
- Manual Claude CLI calls can return output when invoked directly, but tool access/path behavior needs tightening before relying on it for large scans.

Recommended next step:

1. Fix or simplify `.ai_agents/scripts/run-claude-task.ps1`.
2. Run `.ai_agents/tasks/smoke-test.md`.
3. If report is non-empty and accurate, run:
   - `.ai_agents/tasks/asset-doc-cleanup-audit.md`
   - `.ai_agents/tasks/docs-rewrite-plan.md`
   - `.ai_agents/tasks/code-redundancy-review.md`
4. Codex implements only after reviewing reports.

## User Intent Next

User wants:

- Audit `public/`, `resources/`, images, icons, static assets.
- Identify frontend usage and replace non-owned/template assets.
- Check redundant/unreasonable code.
- Re-check image generation / preview generation chain.
- Produce a test report.
- Reorganize `README.md`, `handover_brief.md`, and `docs/*.md`; remove obsolete migration docs.

## Caution

Do not let external agents directly edit production files. Use reports/patch proposals only.
