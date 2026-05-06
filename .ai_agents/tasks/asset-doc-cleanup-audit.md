# Asset, Document, and Redundancy Audit

## Scope

Project root:

`D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge`

Exclude:

- `node_modules`
- `.next`
- `.venv`
- `forge_runtime`
- `__pycache__`
- `tsconfig.tsbuildinfo`

## Objectives

1. Inventory static assets in `public/` and `resources/`.
2. Identify which assets are referenced by `app/`, `components/`, `lib/`, `docs/`, `README.md`, and `handover_brief.md`.
3. Flag assets that appear to come from templates, old Text2BIM, next-ai-draw-io, demos, placeholders, or third-party samples.
4. Review user-visible frontend pages for old names, placeholder logos, mock text, and stale routes.
5. Review docs and recommend a new documentation structure.
6. Review image/preview generation paths for BIM/WebGL/IFC artifacts.

## Required Output

### Static Asset Inventory

Table columns:

`Asset path | Type | Referenced? | Reference locations | Risk | Recommendation`

### Frontend Display Issues

Table columns:

`File path | Visible issue | User impact | Recommendation`

### Redundant or Risky Code

Group findings into:

- `Must keep compatibility layer`
- `Safe to delete`
- `Needs confirmation`
- `Do not touch`

### Image / Preview Generation Chain

Table columns:

`Entry | Generated artifact | Output path | Frontend consumer | Test method | Risk`

### Test Plan

Table columns:

`Test | Steps | Expected result | Failure diagnostics`

### Documentation Plan

Table columns:

`Document path | Current purpose | Problem | Recommendation | New destination`

### Priority Plan

Use `P0`, `P1`, `P2`.

Do not output large code snippets.
