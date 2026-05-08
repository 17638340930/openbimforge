# Documentation Agent Rules

Scope: this file applies to all files under `docs/`.

## Source of truth

- `docs/nexus_full_pipeline_map.md` is the current authoritative architecture and pipeline document.
- If code changes touch ForgeVision, Nexus stages, Vectorworks VM execution, payload lifecycle, or agent prompts, update `docs/nexus_full_pipeline_map.md`.
- Keep `README.md` short. Link to detailed docs instead of duplicating long architecture sections.

## Style

- Write documentation in clear Chinese unless the file is explicitly for English-only external users.
- Use exact repository-relative or absolute file paths when referencing code.
- Include line numbers when describing current code behavior.
- Distinguish clearly between:
  - implemented
  - partially implemented
  - planned
  - deprecated

## Safety

- Do not claim a chain is tested unless there is a real test log, generated file, or explicit manual verification.
- Do not present external Agent/Gemini audit reports as source of truth without checking the code.
- Do not delete legacy notes unless they are replaced by an indexed document or moved to an archive.

## Current terminology

- `ForgeVision-Form`: image-to-massing chain; currently implemented.
- `CAD-First`: high-precision branch inside ForgeVision-Form; currently implemented.
- `ForgeVision-Layout`: floor-plan / room-topology chain; planned, not fully implemented.
- `Stage4`: Vectorworks Web Palette / VLB / VM execution layer.
