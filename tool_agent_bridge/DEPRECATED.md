# tool_agent_bridge — Deprecated Compatibility Layer

## Status

**Deprecated. Retained only for binary compatibility with the current
Vectorworks `.vlb` plugin.** Do not add new code here.

## What this package is

Every file in this directory is a one-line re-export of the matching
module in [`forge_core/build_agent/`](../forge_core/build_agent/):

| File | Re-exports |
|------|------------|
| `adapter_entry.py` | `forge_core.build_agent.adapter_entry` |
| `unified_runtime.py` | `forge_core.build_agent.unified_runtime` |
| `vectorworks_execute.py` | `forge_core.build_agent.vectorworks_execute` |
| `vectorworks_watch_runner.py` | `forge_core.build_agent.vectorworks_watch_runner` |
| `vectorworks_capability_scan.py` | `forge_core.build_agent.vectorworks_capability_scan` |

The `__init__.py` additionally patches `__path__` so Python's import
machinery resolves `tool_agent_bridge.<name>` to the canonical
`forge_core.build_agent.<name>` package.

## Why it exists

The project was originally named `Text2BIM` and shipped a Python package
called `tool_agent`. The Vectorworks 2024 `.vlb` plugin binary
(`vectorworks_plugin/openBIMForge2024/WebPaletteTUM.vlb`) was compiled
with hardcoded `import tool_agent_bridge.*` statements. Until the
`.vlb` is rebuilt against the `forge_core.build_agent.*` namespace, these
re-exports must stay.

## Callers that still depend on this package

- `vectorworks_plugin/openBIMForge2024/tool_agent/vs_interface.py`
- `forge_core/design_agent/vs_interface.py` (legacy bridge path)
- `lib/bim/forge-architect-adapter.ts` (builds a capability-scan script
  literal that imports from `tool_agent_bridge`)
- `app/api/bim/forge-architect-capabilities/route.ts` (same)

## Removal plan

1. Rebuild `WebPaletteTUM.vlb` with direct `forge_core.build_agent`
   imports. Owned by the Vectorworks plugin maintainer.
2. Patch the two `.ts` capability-scan script builders to reference the
   new namespace.
3. Patch `forge_core/design_agent/vs_interface.py` to call
   `forge_core.build_agent.vectorworks_watch_runner` directly.
4. Delete this directory.

## Do not

- Add new modules here.
- Implement logic in these re-exports. If you need to add behaviour for
  the VM bridge, add it in `forge_core/build_agent/` and let the
  re-export pick it up automatically.
- Import `tool_agent_bridge.*` from new code. Use
  `forge_core.build_agent.*` directly.
