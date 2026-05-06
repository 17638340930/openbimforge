# Code Redundancy Review

Review the openBIMForge codebase for redundant or shallow modules after Nexus
Stage 4 is working.

Focus on:

- `app/api/bim/*`
- `app/bim/*`
- `components/chat-message-display.tsx`
- `components/chat-panel.tsx`
- `contexts/dev-log-store.tsx`
- `lib/bim/*`
- `forge_core/build_agent/*`
- `forge_core/design_agent/runtime_config.py`
- `vectorworks_plugin/openBIMForge2024/**`

Classify:

- compatibility layers that must stay
- pass-through routes that can stay but should be documented
- modules safe to delete
- modules that need tests before refactor
- stale debug logs
- old environment variables that are only compatibility aliases

Output concise markdown with concrete file paths and recommendations.
