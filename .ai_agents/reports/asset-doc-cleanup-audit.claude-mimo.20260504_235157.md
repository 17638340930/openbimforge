Now I have all the data needed. Let me compile the full audit report.

---

# openBIMForge — Asset, Document, and Redundancy Audit Report

**Auditor**: External Review Agent
**Date**: 2026-05-04
**Project root**: `D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge`
**Branch**: `codex-stage-a-clarification-loop`

---

## 1. Static Asset Inventory

| Asset path | Type | Referenced? | Reference locations | Risk | Recommendation |
|---|---|---|---|---|---|
| `public/architecture.png` | OG image | Yes | `app/[lang]/layout.tsx:93,104` (OpenGraph/Twitter meta) | Low — serves as social preview card | Keep. Replace with openBIMForge-branded screenshot when available. |
| `public/favicon.ico` | Favicon | Yes | `app/[lang]/layout.tsx:118` | Low | Keep. |
| `public/favicon-192x192.png` | PWA icon | Yes | `app/manifest.ts:15` | Low | Keep. |
| `public/favicon-512x512.png` | PWA icon | Yes | `app/manifest.ts:21` | Low | Keep. |
| `public/favicon-white.svg` | SVG favicon | **No** | Not referenced anywhere in code | **Medium** — dead asset, possibly from template | **Delete.** |
| `public/doubao-color.png` | Doubao (ByteDance) logo | **No** | Not referenced in code | **High** — third-party brand asset with no usage | **Delete.** |
| `public/doubao-color.svg` | Doubao SVG logo | **No** | Not referenced in code | **High** — third-party brand asset | **Delete.** |
| `public/doubao-color.svg-nexus-legacy-bak` | Doubao SVG backup | **No** | Not referenced | **High** — leftover backup of third-party logo | **Delete.** |
| `public/example.png` | Example screenshot | **No** | Only in `lib/base-path.ts` JSDoc comment (docstring example) | **Medium** — placeholder/demo asset | **Delete.** |
| `public/live-demo-button.svg` | Demo button badge | **No** | Not referenced in code | **High** — from next-ai-draw-io template | **Delete.** |
| `public/volcengine-invite.png` | Volcengine invite banner | **No** | Not referenced in code | **High** — ByteDance/Volcengine marketing asset | **Delete.** |
| `public/chain-of-thought.txt` | Academic paper summary | **No** | Only in `lib/base-path.ts` JSDoc comment | **Medium** — not a BIM asset, research artifact | **Delete** or move to `docs/`. |
| `public/_headers` | CDN cache headers | Yes (implicit) | Deployed by Next.js/Cloudflare | Low | Keep. |
| `resources/icon.png` | Electron/macOS app icon | **No** | Not referenced by Next.js or any frontend code | **Low** — appears to be a macOS Electron resource | **Delete** unless Desktop app is planned. |
| `resources/entitlements.mac.plist` | macOS code signing entitlements | **No** | Not referenced by any code | **Low** — Electron/macOS artifact | **Delete** unless Desktop app is planned. |

---

## 2. Frontend Display Issues

| File path | Visible issue | User impact | Recommendation |
|---|---|---|---|
| `app/[lang]/layout.tsx:76` | `metadataBase` hardcoded to `http://localhost:6002` | OG image links break in production deployment; social previews will fail | Make dynamic from `NEXT_PUBLIC_APP_URL` env var or `headers()`. |
| `app/[lang]/layout.tsx:93` | OG image URL `/architecture.png` uses absolute path without base path | Broken image on subdirectory deployments | Use `getAssetUrl("/architecture.png")`. |
| `app/[lang]/layout.tsx:152` | JSON-LD `url` hardcoded to `http://localhost:6002` | Schema.org structured data will be wrong in production | Make dynamic. |
| `app/[lang]/page.tsx:10` | Hardcodes `localStorage.setItem("openbimforge-locale", "zh")` | Always forces Chinese locale, ignoring the i18n URL-based locale | Remove or use the `lang` param from the URL. |
| `app/[lang]/page.tsx:26` | Loading fallback text is hardcoded Chinese: `"正在加载 openBIMForge BIM 工作台..."` | Non-Chinese users see Chinese loading text | Use dictionary-based i18n string. |
| `app/bim/vectorworks/vectorworks-console.tsx:337` | `bimChatUrl` hardcoded to `"/zh?openBIMForge=1&mode=nexus"` | Ignores user locale, always routes to `/zh` | Use detected locale or pass through. |
| `app/bim/ifc-viewer/page.tsx:191` | IFC preview note: `"3D Constructive View (Three.js/web-ifc) integration pending"` | Users see an unfinished feature notice | Remove the note or implement the feature. |
| `public/chain-of-thought.txt` | Accessible at `/chain-of-thought.txt` | Exposes internal research notes to anyone | Remove from `public/`. |

---

## 3. Redundant or Risky Code

### Must keep compatibility layer

| Item | Reason |
|---|---|
| `tool_agent/__init__.py` | Python import compatibility shim — redirects `import tool_agent` to `forge_core/design_agent`. Active use in `vectorworks_plugin/openBIMForge2024/tool_agent/vs_interface.py`. |
| `tool_agent_bridge/` (5 files) | Full copy of `forge_core/build_agent/`. The vectorworks plugin's `vs_interface.py` imports from `tool_agent_bridge`. Must remain until plugin is updated. |
| `app/api/bim/text2bim*/` routes (5 re-export files) | Thin re-exports to `forge-architect-*` equivalents. Required by older Vectorworks `.vlb` plugin that calls `/api/bim/text2bim-runner`, `/api/bim/text2bim-capabilities`, etc. |
| `getAllPlantDataV2` function name | Protocol identifier in `.vlb` native bridge. Must not rename. |
| `__OPENBIMFORGE_RUN_ONCE__` | One-time synthesis flag used by `vs_interface.py`. Must not rename. |
| `forge_core/design_agent/muti_agent_prompt/` | Typo in directory name (`muti` vs `multi`), but the `coder_chat_prompt_temp.txt` and `po_chat_prompt_temp.txt` inside are referenced by the agent system. |
| `forge_core/design_agent/Solibri_workflow_xml.xml` | Used by `solibri_checker.py`. Keep for Solibri validation integration. |

### Safe to delete

| Item | Reason |
|---|---|
| `public/doubao-color.png` | Third-party ByteDance logo, unreferenced. |
| `public/doubao-color.svg` | Same. |
| `public/doubao-color.svg-nexus-legacy-bak` | Backup file of above. |
| `public/example.png` | Placeholder image from template project. |
| `public/live-demo-button.svg` | Template demo badge from next-ai-draw-io. |
| `public/volcengine-invite.png` | ByteDance/Volcengine marketing asset. |
| `public/favicon-white.svg` | Unreferenced SVG favicon variant. |
| `resources/icon.png` | macOS Electron icon, not used by Next.js. |
| `resources/entitlements.mac.plist` | macOS entitlements, not used by Next.js. |
| `forge_core/design_agent/test_code.py` | Test file in production source tree. |
| All `__pycache__/` directories | Should be in `.gitignore`. |

### Needs confirmation

| Item | Question |
|---|---|
| `forge_core/design_agent/solibri_checker.py` + `Solibri_workflow_xml.xml` | Is Solibri integration actively used or planned? If not, safe to delete. |
| `forge_core/design_agent/speech2text.py` | Voice input is supported on frontend (`useVoiceInput` hook), but this Python module may be unused. Confirm if the Python side uses speech-to-text. |
| `forge_core/design_agent/python_interpreter.py` | Appears to be a standalone interpreter. Confirm if it's called by the agent pipeline. |
| `forge_core/design_agent/multi_agent_prompt/` vs `muti_agent_prompt/` | Two directories with similar names. `multi_agent_prompt/` contains `po_chat_prompt_temp.txt` and `coder_prompt_temp.txt`. `muti_agent_prompt/` contains `coder_chat_prompt_temp.txt`, `po_chat_prompt_temp.txt`, `checker_chat_prompt_temp.txt`, `floor_plan_designer_chat_prompt_few_shots.txt`. Which is canonical? |
| `RUN_IN_VECTORWORKS_START_FRONTEND.py` | Contains hardcoded `PROJECT_ROOT = Path(r"D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge")`. Is this used? If so, the hardcoded path is a deployment risk. |
| `forge_core/design_agent/vs.py` | Appears to be a `vs` module stub for Vectorworks SDK. Confirm it's the same as `vs_interface.py` or a different purpose. |

### Do not touch

| Item | Reason |
|---|---|
| `vectorworks_plugin/openBIMForge2024/WebPaletteTUM.vlb` | Compiled native plugin binary. Cannot be edited; must be rebuilt from C++ source. |
| `vectorworks_plugin/openBIMForge2024/WebPaletteTUM.vwr/html/main.js` | Webpack-bundled, minified communication layer for the Vectorworks Web Palette. Editing requires rebuild. |
| `forge_core/design_agent/vs_interface.py` + `vectorworks_plugin/.../tool_agent/vs_interface.py` | These are the `vs` module bridge for Vectorworks Python execution. Critical for Stage 4. |
| `forge_core/build_agent/vectorworks_execute.py` | The actual Vectorworks Python execution engine (`run_handoff()`). |
| `forge_core/build_agent/vectorworks_watch_runner.py` | File-watching runner for Vectorworks. |

---

## 4. Image / Preview Generation Chain

| Entry | Generated artifact | Output path | Frontend consumer | Test method | Risk |
|---|---|---|---|---|---|
| `forge-architect-adapter.ts` spawn Python | `nexus_payload_*.json` (Transit-Payload) | `os.tmpdir()` (temp) | `forge-architect-runner` API | Send BIM request, check handoffs dir | Low — temp file cleaned up |
| `adapter_entry.py` Stage 3 | `nexus_payload_{ts}.json` | `forge_runtime/handoffs/` | `forge-architect-runner` route, `vectorworks-console.tsx` polling | Check `forge_runtime/handoffs/` for new JSON | Low |
| `vectorworks_execute.py` Stage 4 | `.done`, `.result.json` | `forge_runtime/handoffs/` | `forge-architect-result` route, `ExecutionCard` polling | Run in Vectorworks, check `.result.json` | **P0 blocked** — Stage 4 not actually executing |
| Vectorworks IFC export | `.ifc` file | `forge_runtime/artifacts/` (or Vectorworks-controlled) | `bim/ifc-viewer/page.tsx`, `forge-architect-artifact` route | Check `ifc_ready` in `.result.json` | **P0 blocked** — depends on Stage 4 |
| Vectorworks VWX save | `.vwx` file | `forge_runtime/artifacts/` | `forge-architect-artifact` route (download link) | Same as IFC | **P0 blocked** — depends on Stage 4 |
| `vectorworks_capability_scan.py` | `vectorworks_styles.json` | `forge_runtime/capabilities/` | `forge-architect-capabilities` route, `vectorworks-console.tsx` capability card | Run scan script in Vectorworks | Low |
| Layout-Agent (`useImageUpload` + `runLayout`) | Layout metadata JSON | In-memory only | `chat-panel.tsx` → `ExecutionCard` | Upload image, click "交付 Visionary" | Low |

**Key finding**: The entire preview/artifact chain from Stage 4 onward is blocked because the Vectorworks VM execution is not actually running. The frontend correctly polls for results, but no artifacts are ever produced in dry-run mode.

---

## 5. Test Plan

| Test | Steps | Expected result | Failure diagnostics |
|---|---|---|---|
| **T0: Dev server starts** | Run `.\scripts\start_dev.ps1` | Next.js on `http://localhost:6002`, no build errors | Check `node_modules` installed, `npm install` first |
| **T1: Chat page loads** | Navigate to `/zh` | Chat panel renders, "Nexus-Orchestration Center" visible | Check `app/[lang]/page.tsx` and layout |
| **T2: Model selector works** | Click settings icon → model config | Model list populates, can select provider/model | Check `model-config-dialog.tsx`, `ai-providers.ts` |
| **T3: BIM clarification loop** | Type "设计一个办公楼" (incomplete) | System asks for missing slots (storey count, area, etc.) | Check `clarification-loop.ts`, `route.ts` Stage 0 |
| **T4: BIM generation (dry-run)** | Type full prompt with all params | Execution card shows 4 stages, all completed in ~30-60s | Check Python process spawn, `adapter_entry.py` stderr output |
| **T5: Execution card rendering** | After T4, expand execution card | Stage icons, durations, quality score visible | Check `chat-message-display.tsx` `ExecutionCard` |
| **T6: Console page loads** | Navigate to `/bim/vectorworks?host=vectorworks` | Status badges, capability card, runner status visible | Check `vectorworks-console.tsx` |
| **T7: IFC viewer (no data)** | Navigate to `/bim/ifc-viewer` | Shows "IFC path parameter is missing" message | Expected behavior |
| **T8: Legacy text2bim API** | POST to `/api/bim/text2bim` with query | Forwards to Nexus adapter, returns result | Check `text2bim/route.ts` re-export |
| **T9: Vectorworks VM integration** | Open Web Palette in Vectorworks, send request | `window.tumIntegrator` detected, Runner starts | **P0**: Verify `.vlb` exposes `openBIMForgeRunPending` |
| **T10: Stage 4 full chain** | In Vectorworks, BIM request → VWX + IFC produced | `.result.json` shows `ok: true`, artifacts exist | **P0**: Blocked until `.vlb` integration confirmed |
| **T11: i18n consistency** | Switch between `/en`, `/zh`, `/ja`, `/zh-Hant` | All UI text matches selected locale | Check `lib/i18n/dictionaries.ts` completeness |
| **T12: Subdirectory deploy** | Set `NEXT_PUBLIC_BASE_PATH=/openbimforge` | All API calls and asset URLs include prefix | Check `lib/base-path.ts` integration |

---

## 6. Documentation Plan

| Document path | Current purpose | Problem | Recommendation | New destination |
|---|---|---|---|---|
| `README.md` | Project overview, architecture, deployment | Good but references `LongCat` model in test docs (in `FULL_CHAIN_TEST.md`) and has stale model recommendations | Update model recommendations, add links to all docs | Keep at root |
| `handover_brief.md` | Detailed handover for successor | Comprehensive, but Stage 4 status may become stale as blockers are resolved | Update after each Stage 4 milestone | Keep at root, update incrementally |
| `docs/FULL_CHAIN_TEST.md` | End-to-end test procedure | References `text2bim_handoff_*` file naming (legacy), references `LongCat-Flash-Chat` model, mentions "do not delete Text2BIM-main" | Update file naming to `nexus_payload_*`, remove stale model refs | `docs/` |
| `docs/MIGRATION_PHASE_1.md` | Migration planning | Describes initial scaffold creation. Migration is mostly complete. | Mark as **completed** or archive. | `docs/archive/` |
| `docs/PATH_MIGRATION_REFERENCE.md` | Path mapping reference | Still useful for protocol compatibility notes. "Names To Remove Later" section is partially done. | Update progress, mark completed items | `docs/` |
| `docs/GEMINI_RELAY_PROMPTS.md` | Gemini scanning prompts | Contains instructions for external AI tool. Operational doc, not user-facing. | Keep as-is or move to `.ai_agents/` | `.ai_agents/` or delete if scanning is done |
| `docs/VECTORWORKS_PLUGIN_INSTALL.md` | Plugin installation guide | Good, comprehensive, current | Keep | `docs/` |
| `public/chain-of-thought.txt` | Academic paper summary | Not documentation, not a static asset. Exposed at public URL. | Move to `docs/research/` or delete | `docs/research/` or delete |

**Recommended new documentation structure**:

```
docs/
  VECTORWORKS_PLUGIN_INSTALL.md   (keep)
  FULL_CHAIN_TEST.md              (update)
  PATH_MIGRATION_REFERENCE.md     (update)
  STAGE_4_IMPLEMENTATION.md       (new — Stage 4 .vlb integration plan)
  archive/
    MIGRATION_PHASE_1.md          (completed)
```

---

## 7. Priority Plan

### P0 — Blocks core functionality

| # | Finding | Action |
|---|---|---|
| 1 | **Stage 4 not executing** — `.vlb` plugin `openBIMForgeRunPending` method availability unknown | Confirm method exists in `.vlb`. If not, implement polling in `index.html` per `handover_brief.md` Step 1-3. |
| 2 | **7 dead public assets** (doubao, example, volcengine, live-demo, favicon-white) | Delete all 7 unreferenced assets from `public/`. Third-party logos pose brand/legal risk. |
| 3 | **`metadataBase` and JSON-LD hardcoded to `localhost:6002`** | Make dynamic from env var. Breaks all OG previews and structured data in production. |

### P1 — Affects user experience or maintenance

| # | Finding | Action |
|---|---|---|
| 4 | **`page.tsx` forces locale to `"zh"`** | Remove hardcoded locale setter; use i18n URL param. |
| 5 | **`vectorworks-console.tsx` hardcodes `/zh` in chat URL** | Use detected locale. |
| 6 | **Duplicate `muti_agent_prompt/` vs `multi_agent_prompt/`** | Consolidate into one directory with correct spelling. |
| 7 | **`RUN_IN_VECTORWORKS_START_FRONTEND.py` hardcoded path** | Use `__file__` resolution or env var. |
| 8 | **`resources/` directory with Electron artifacts** | Delete `resources/icon.png` and `resources/entitlements.mac.plist` unless Desktop app is planned. |
| 9 | **Stale docs** — `MIGRATION_PHASE_1.md`, `FULL_CHAIN_TEST.md` model refs | Archive completed migration docs, update test docs. |
| 10 | **`public/chain-of-thought.txt` exposed** | Move to `docs/` or delete. |

### P2 — Cleanup and polish

| # | Finding | Action |
|---|---|---|
| 11 | **`__pycache__/` dirs in source tree** | Add to `.gitignore`, remove tracked instances. |
| 12 | **`forge_core/design_agent/test_code.py`** | Move to `tests/` or delete. |
| 13 | **`tool_agent_bridge/` is a full copy of `forge_core/build_agent/`** | After Vectorworks plugin imports are migrated, delete `tool_agent_bridge/`. |
| 14 | **`solibri_checker.py` + `Solibri_workflow_xml.xml`** | Confirm usage. Delete if unused. |
| 15 | **IFC viewer note "integration pending"** | Implement Three.js/web-ifc viewer or remove the note. |

---

*End of audit report.*
