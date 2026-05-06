I now have a complete picture of the codebase. Here is the review report.

---

# openBIMForge Code Redundancy Review

## 1. Modules Safe to Delete

### `tool_agent_bridge/` — entire package (5 modules)

All files except `__init__.py` are single-line re-exports:

| File | Content |
|------|---------|
| `adapter_entry.py` | `import forge_core.build_agent.adapter_entry as core_entry` |
| `unified_runtime.py` | `from forge_core.build_agent.unified_runtime import *` |
| `vectorworks_execute.py` | `from forge_core.build_agent.vectorworks_execute import *` |
| `vectorworks_watch_runner.py` | `from forge_core.build_agent.vectorworks_watch_runner import *` |
| `vectorworks_capability_scan.py` | `from forge_core.build_agent.vectorworks_capability_scan import *` |

`__init__.py` redirects `__path__` to `forge_core/build_agent`. **Blocker**: 4 import sites still reference `tool_agent_bridge.*` — update these first:

- `lib/bim/forge-architect-adapter.ts:55` — Python string literal
- `app/api/bim/forge-architect-capabilities/route.ts:34` — Python string literal
- `forge_core/design_agent/vs_interface.py:167, 200`
- `vectorworks_plugin/openBIMForge2024/tool_agent/vs_interface.py:180`

### `forge_core/design_agent/multi_agent_prompt/` — empty duplicate directory

Both `po_chat_prompt_temp.txt` and `coder_prompt_temp.txt` are **0 bytes**. The real prompts live in `muti_agent_prompt/`. Delete `multi_agent_prompt/` entirely.

### `app/bim/text2bim-status/page.tsx` — pure redirect

One-liner that redirects to `/bim/nexus-status`. Safe to delete after confirming no external links reference `/bim/text2bim-status`.

## 2. Pass-Through Routes (keep, but document)

These 4 API routes are single-line re-exports maintaining backward compatibility with older Vectorworks plugins and the legacy `text2bim` naming:

| Route | Re-exports from |
|-------|----------------|
| `app/api/bim/text2bim-artifact/route.ts` | `forge-architect-artifact` |
| `app/api/bim/text2bim-capabilities/route.ts` | `forge-architect-capabilities` |
| `app/api/bim/text2bim-fix/route.ts` | `forge-architect-fix` |
| `app/api/bim/text2bim-result/route.ts` | `forge-architect-result` |
| `app/api/bim/text2bim-runner/route.ts` | `forge-architect-runner` |

**Recommendation**: Add a `@deprecated` JSDoc comment and a console.warn on each, or consolidate into a single Next.js middleware rewrite rule.

## 3. Compatibility Layers That Must Stay

### `vectorworks_plugin/openBIMForge2024/tool_agent/vs_interface.py`

This is the Vectorworks `.vlb` entry point. It proxies to `forge_core/design_agent/vs_interface.py` via `importlib`, handles the `__OPENBIMFORGE_RUN_ONCE__` command, writes diagnostic probe files, and bridges legacy `getAllPlantDataV2` calls. **Must stay** until the `.vlb` plugin is rebuilt.

### `vectorworks_plugin/openBIMForge2024/tool_agent/speech2text.py`

Compatibility proxy for `.vlb` speech bridge imports. Must stay alongside the plugin.

### `app/api/bim/text2bim/route.ts`

Unlike the other text2bim routes, this one has its own logic — it maps legacy `chat_history`/`session_id` fields to the Nexus schema and calls `runNexusArchitectAdapter`. Must stay as a compatibility bridge.

### `forge_core/design_agent/runtime_config.py`

The `_env()` helper with `TEXT2BIM_*` fallbacks is the compatibility layer for legacy environment variables. See section 6 below.

## 4. Modules That Need Tests Before Refactor

### `forge_core/build_agent/unified_runtime.py`

Contains the core multi-provider agent factory (`create_unified_agent`), provider normalization, and the `run_nexus_architect_pipeline` function. No unit tests exist. The agent creation logic branches on 4+ providers with custom HTTP client injection. Needs tests before any refactor.

### `forge_core/build_agent/vectorworks_execute.py`

816 lines covering code validation, static rewriting, retry logic, heuristic error fixing, and IFC export. The `_static_validate_and_rewrite_code` and `_apply_heuristic_fix` functions are particularly complex. No tests.

### `forge_core/build_agent/adapter_entry.py`

The `extract_semantic_slots` function duplicates regex logic from `lib/bim/clarification-loop.ts` (TypeScript side). Both extract building type, storey count, area, and floor height. A refactor should unify these or document why they diverge.

### `lib/bim/clarification-loop.ts`

270 lines of regex-based slot extraction. Well-structured but has no tests. The `evaluateClarificationNeed` function is a critical decision point for the Stage A flow.

### `lib/bim/forge-architect-adapter.ts`

567 lines handling the Python bridge spawn, progress streaming, and JSON parsing. The `spawnBridgeProcess` function is the most complex piece — it manages child process lifecycle, timeout, stderr parsing, and stage event emission. Needs integration tests.

## 5. Stale Debug Logs

### `vectorworks_plugin/openBIMForge2024/tool_agent/vs_interface.py`

Writes probe files to `forge_runtime/handoffs/` on every import and every call:

- `openbimforge_vs_interface_import_probe.json` (line 44) — written at **module import time**
- `openbimforge_vs_interface_call_probe.json` (line 185) — written on every `excute_webpalette_po_coder` call
- `openbimforge_legacy_bridge_status.json` — written on every status change

These accumulate in the handoffs directory and are never cleaned up.

### `forge_core/design_agent/vs_interface.py`

Writes the same `openbimforge_vs_interface_import_probe.json` pattern (lines 9-39).

### `forge_core/build_agent/forge-architect-result/route.ts`

`console.log` at line 57-70 logs the full `logVmWaitState` on every 202 response. With polling, this can generate hundreds of log lines per session. The `vmWaitLogCache` deduplicates identical states, but the log output itself is verbose.

### `forge_core/build_agent/adapter_entry.py`

`log_progress()` writes every orchestration step to stderr. While useful for diagnostics, it produces ~30+ lines per request. Consider gating behind a `DEBUG` flag.

### `forge_core/build_agent/unified_runtime.py`

`log_progress()` and `emit_stage_event()` both write to stderr. The `[Diagnostics]` line at line 379 leaks the API key length (`len(api_key)`), which is a minor information disclosure.

## 6. Old Environment Variables (Compatibility Aliases)

The following `TEXT2BIM_*` variables exist only as legacy fallbacks in `forge_core/design_agent/runtime_config.py`:

| Legacy (`TEXT2BIM_*`) | Current (`OPENBIMFORGE_*`) | Used in |
|---|---|---|
| `TEXT2BIM_LLM_CONFIG_JSON` | `OPENBIMFORGE_LLM_CONFIG_JSON` | `runtime_config.py:77` |
| `TEXT2BIM_LLM_PROVIDER` | `OPENBIMFORGE_LLM_PROVIDER` | `runtime_config.py:80` |
| `TEXT2BIM_LLM_MODEL_ID` | `OPENBIMFORGE_LLM_MODEL_ID` | `runtime_config.py:81` |
| `TEXT2BIM_LLM_BASE_URL` | `OPENBIMFORGE_LLM_BASE_URL` | `runtime_config.py:82` |
| `TEXT2BIM_LLM_API_KEY` | `OPENBIMFORGE_LLM_API_KEY` | `runtime_config.py:83` |
| `TEXT2BIM_VERTEX_API_KEY` | `OPENBIMFORGE_VERTEX_API_KEY` | `runtime_config.py:84` |
| `TEXT2BIM_WORKFLOW_MODEL` | `OPENBIMFORGE_WORKFLOW_MODEL` | `runtime_config.py:110` |
| `TEXT2BIM_EXECUTION_MODE` | `OPENBIMFORGE_EXECUTION_MODE` | `runtime_config.py:115` |
| `TEXT2BIM_SOLIBRI_PATH` | `OPENBIMFORGE_SOLIBRI_PATH` | `runtime_config.py:118` |
| `TEXT2BIM_OUTPUT_ROOT` | `OPENBIMFORGE_OUTPUT_ROOT` | `runtime_config.py:121` |
| `TEXT2BIM_TASK_NUMBER` | `OPENBIMFORGE_TASK_NUMBER` | `runtime_config.py:122` |
| `TEXT2BIM_TASK_ROUND` | `OPENBIMFORGE_TASK_ROUND` | `runtime_config.py:123` |
| `TEXT2BIM_PROJECT_ROOT` | `OPENBIMFORGE_ROOT` | `vectorworks_execute.py:668` |

Additionally, `adapter_entry.py:210-217` actively **sets** `TEXT2BIM_*` env vars as copies of the `OPENBIMFORGE_*` vars, for backward compatibility with code that reads them.

**Recommendation**: After Nexus Stage 4 is stable, add a deprecation log when `TEXT2BIM_*` fallbacks are hit, then remove after one release cycle.

## 7. Security Issue

### `forge_core/design_agent/multi_agents_workflow.py:21`

```python
os.environ['DEEPSEEK_API_KEY'] = 'sk-2b929de8fbf34b6e9be05091bb691439'
```

**Hardcoded API key in source code.** This file appears to be the legacy workflow that is no longer in the active pipeline (superseded by `unified_runtime.py`). Should be deleted or the key rotated immediately.

## 8. Other Observations

### `vectorworks_plugin/openBIMForge2024/WebPaletteTUM.vwr/html/main.js`

610KB bundled JS file checked into the repo. This is likely a build artifact. Should be in `.gitignore` or built in CI.

### Duplicate `extract_semantic_slots`

- `forge_core/build_agent/adapter_entry.py:62-87` — Python implementation
- `lib/bim/clarification-loop.ts:166-175` — TypeScript implementation

Both extract building_type, storey_count, target_area, floor_height from natural language. The Python version is less comprehensive (fewer building type tokens, no normalization). Consider unifying or documenting the divergence.

### `forge_core/design_agent/` — legacy files

These files are from the pre-Nexus architecture and are not imported by the active pipeline:

- `multi_agents_workflow.py` (contains hardcoded API key)
- `solibri_checker.py`
- `test_code.py`
- `python_interpreter.py`
- `floor_plan_designer_chat_prompt_few_shots.txt` (in `muti_agent_prompt/`)

They should be archived or deleted once Nexus Stage 4 is confirmed stable.
