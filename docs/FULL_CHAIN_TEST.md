# openBIMForge Full Chain Test

Author: JY

This document is the current end-to-end test path for the unified `openBIMForge` folder.

## Goal

Validate this chain:

```text
Vectorworks Web Palette
  -> openBIMForge Next.js chat
  -> Design Agent
  -> Handoff Package
  -> Vectorworks Runner
  -> VWX / IFC artifacts
  -> frontend execution-flow card / IFC actions
```

## 1. Start The New Frontend

From PowerShell:

```powershell
cd D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge
.\scripts\start_dev.ps1
```

Expected:

- Next.js starts on `http://localhost:6002`.
- The Web Palette URL can load `/bim/vectorworks?host=vectorworks`.
- The chat entry can load `/zh?openBIMForge=1&mode=text2bim&host=vectorworks`.

## 2. Install Vectorworks Python Paths

Run once after moving the project folder:

```powershell
cd D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge
.\scripts\install_vectorworks_paths.ps1
```

Expected output includes:

```text
C:\Users\92586\AppData\Roaming\Nemetschek\Vectorworks\2024\Python Externals\openbimforge.pth
```

Then restart Vectorworks.

## 3. Install The Web Palette

Use the copied plugin folder:

```text
D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge\vectorworks_plugin\openBIMForge2024
```

Install or link it into the Vectorworks user Plug-ins directory:

```text
C:\Users\92586\AppData\Roaming\Nemetschek\Vectorworks\2024\Plug-ins
```

After restart, open:

```text
Window > Palettes > Web Palettes > openBIMForge
```

## 4. Clean Runtime For A First-Use Simulation

Only delete files under the new runtime folder:

```text
D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge\forge_runtime\handoffs
```

Do not delete `Text2BIM-main` or `next-ai-draw-io-main`; they are the working fallback versions.

## 5. Test From Vectorworks

1. Open the `openBIMForge` Web Palette.
2. Confirm the console shows capability status and Runner status.
3. Click into BIM chat.
4. Use a small prompt first:

```text
生成一个办公楼方案，6层，总面积4200平方米，层高3.6米。
```

Expected:

- The execution card shows Design Agent / Programmer / State Store / Handoff Package.
- A handoff JSON appears in `forge_runtime\handoffs`.
- Vectorworks Runner consumes the handoff and creates `.running`, `.done`, `.result.json`.
- VWX and IFC artifacts are written under `forge_runtime\artifacts` unless Vectorworks requires an IFC export dialog confirmation.

## 6. If The Card Stays At 4/5

That means the frontend has generated the handoff, but it has not yet observed the Vectorworks Runner result.

Check:

```text
D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge\forge_runtime\handoffs
```

Expected final files:

- `text2bim_handoff_*.json`
- `text2bim_handoff_*.running` during execution only
- `text2bim_handoff_*.done`
- `text2bim_handoff_*.result.json`

If `.done` and `.result.json` exist but the card still shows 4/5, the next fix is frontend polling/status reconciliation, not Vectorworks execution.

## 7. Known Model Issue

`LongCat-Flash-Thinking-2601` can timeout during Product Owner planning or chat completion. This is recorded as a model tuning issue and is not blocking the production chain.

Current recommended production model:

```text
LongCat-Flash-Chat
```

