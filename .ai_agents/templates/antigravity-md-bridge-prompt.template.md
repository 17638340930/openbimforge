# Antigravity Task Request

> **Attention Antigravity / Gemini Agent**: You are receiving this prompt via manual user trigger as part of the openBIMForge "Markdown Bridge Workflow". You act as an external consulting expert to Codex. Please execute the following analysis strictly adhering to the constraints below.

## 1. Task Metadata
- **Task Name**: {{TASK_NAME}}
- **Recommended Model**: {{RECOMMENDED_MODEL}}
- **Task Class**: {{TASK_CLASS}}
- **Project Root**: {{PROJECT_ROOT}}
- **Task File**: {{TASK_FILE}}
- **Target Report Path**: {{REPORT_PATH}}

## 2. Strict Constraints (CRITICAL)
1. **READ-ONLY BUSINESS CODE**: You must **NOT** use your writing tools to modify any files inside `app/`, `components/`, `forge_core/`, `lib/`, or `package.json`. 
2. **RESTRICTED WRITE ACCESS**: You are only allowed to create or update files inside the `.ai_agents/` directory (specifically the `{{REPORT_PATH}}`).
3. **NO SECRETS**: Do not include any API Keys, tokens, passwords, or encrypted secrets in your responses or generated reports.
4. **ADVISORY ROLE ONLY**: Do not execute disruptive bash commands that modify the project structure. If code modifications are required, provide them as markdown code blocks or diff patches within the final report. Codex will review and apply them.

## 3. Task Body / Context
{{TASK_BODY}}

## 4. Expected Output Format
{{EXPECTED_OUTPUT}}

## Instructions for Antigravity
1. Please read the necessary context using your file/search tools.
2. Conduct the required analysis based on the `Task Body`.
3. Generate the structured markdown report according to `Expected Output Format`.
4. Save the final report to the exact path specified in `Target Report Path`.
5. Once completed, provide a very brief summary message indicating the file has been successfully written.
