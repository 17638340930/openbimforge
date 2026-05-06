# External Agent Workflow

Codex is the lead implementer. External agents are used for low-cost scanning,
review, and report generation. They must not directly modify production files
unless Codex explicitly asks for a patch file.

## Directory Contract

- `tasks/`: task prompts created by Codex.
- `reports/`: markdown reports written by external agents.
- `patches/`: optional patch proposals. Do not apply automatically.
- `decisions/`: Codex acceptance/rejection notes after review.
- `scripts/`: local wrappers for tools that expose a CLI/API.

## Agent Roles

- `claude-mimo`: code review, architecture review, refactor proposals.
- `gemini-antigravity`: large asset/document inventory when run manually in Antigravity.
- `mimo-docs`: Chinese docs consolidation and README/handover rewrite drafts.

## Rules

1. Reports must include concrete file paths.
2. Deletion recommendations must be classified as `safe`, `needs-confirmation`, or `do-not-delete`.
3. Generated patches must be stored under `patches/` and never applied directly.
4. Runtime folders are out of scope: `node_modules`, `.next`, `.venv`, `forge_runtime`, `__pycache__`.
5. Codex makes final edits and runs validation.
