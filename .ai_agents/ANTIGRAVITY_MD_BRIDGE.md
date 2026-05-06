# Antigravity Markdown Bridge 工作流 (Gemini 3.1 Pro / Flash)

## 1. 角色分工
- **Codex**: 主干调度引擎。负责任务拆分、生成 Task Markdown、生成 Prompt、选择适合的 Gemini 模型，并最终根据报告决定是否执行代码修改。
- **Gemini 3.1 Pro**: 外部专家顾问。负责深度架构分析、复杂 Bug 诊断、跨模块梳理、PRD/ADR 方案设计、安全风险评审。
- **Gemini 3.1 Flash**: 高效扫描器。负责机械性摘要、重复代码扫描、格式化整理、存在性检查、初筛与清单对照。
- **Antigravity GUI**: 用户人工触发和执行 Gemini 模型的环境。不被 Codex 直接进行命令行控制（不走 CDP）。

## 2. 模型分配规则与建议
Codex 在创建任务时，必须在模板中明确 `{{RECOMMENDED_MODEL}}`：
- 推荐使用 `gemini-3.1-pro` 的场景：
  - 跨模块架构审查（例如 Nexus 全链路通讯逻辑）。
  - 复杂 Bug 根因分析（例如 Wasm 与前端通信导致内存溢出）。
  - 性能瓶颈推理、安全边界评估。
  - 综合多个子报告做出最高层级方案建议。
- 推荐使用 `gemini-3.1-flash` 的场景：
  - 静态资产/无效文件存在性检查（如无用的 SVG/PNG 扫描）。
  - 大量重复代码模式扫描。
  - Changelog / Issue Draft 生成。
  - 单一的格式检查与初级 Smoke Review。

## 3. 固定交互流程 (Standard Operating Procedure)
1. **定义任务**: Codex 分析当前需求，生成一份描述具体扫描/分析目标的文件保存至 `.ai_agents/tasks/`。
2. **生成 Prompt**: Codex 根据任务信息和 `.ai_agents/templates/antigravity-md-bridge-prompt.template.md`，生成包含完整参数替换的交互 Prompt（`.md` 格式）。
3. **人工触发**: 用户打开生成的 Prompt，全选复制，并粘贴到 Antigravity GUI 的对话输入框中。
4. **模型选择**: 用户参考 Prompt 顶部的 `{{RECOMMENDED_MODEL}}`，在 Antigravity 界面切换对应的 Pro 或 Flash 模型。
5. **执行分析**: Antigravity/Gemini 执行请求，期间它可调用自身工具独立查阅工作区文件进行分析。
6. **产出报告**: Antigravity 将结论整理为 Markdown 格式，保存至 `.ai_agents/reports/` 目录下（或直接通过工具写入该路径）。
7. **交叉验证**: Codex 读取该报告文件，结合 Claude/opencode 等上下文进行决策。
8. **执行闭环**: Codex 决定是否采纳建议，不自动照单全收；若需修改代码，由 Codex 发起对 `app/`, `components/` 等业务代码的修改。

## 4. 安全边界与约束
- **业务代码只读**：Antigravity 在此工作流中**不允许直接修改** `app`, `components`, `forge_core`, `lib`, `package.json` 等业务文件。它的修改建议必须以补丁（Patch）或代码片段块形式写在报告中，由 Codex 最终实施。
- **仅修改 AI 目录**：Antigravity 的修改权限严格限制在 `.ai_agents/` 及相关的子目录中。
- **密钥阻断**：严禁 Antigravity 在读取或输出时抓取、展示 API Key、Token、Secret 密码。
- **不安装外部包**：禁止在此工作流期间尝试安装 `agm` 或引入破坏原有环境依赖关系的工具包。

## 5. 异常与失败处理
- 若 Antigravity 输出超时或提示文件过大：用户应在聊天框中缩小查阅范围，或让 Codex 重新拆分 Task。
- 若 Antigravity 未生成报告文件：用户应当向 Codex 提供 Antigravity 的最终回答摘要，Codex 负责决定是否要求重试。
- 如果 Antigravity 给出了明显破坏旧架构的提议（例如破坏 Nexus 接口）：Codex 拥有最终否决权，可忽略建议。

## 6. 文件格式与模板约定
- 桥接交互采用 Markdown 作为唯一交换载体。
- 报告骨架约定应包含：`## 背景`、`## 结论`、`## 发现 (Findings)`、`## 方案与补丁 (Patch Plan)`。

---

## 7. Codex 调用话术指南 (供 Codex 遵守)
当需要委托 Antigravity 执行分析时，Codex 的回复应形如：
> “我已经为您生成了面向 Antigravity 的外包分析请求。请复制 `.ai_agents/tasks/AG_TASK_xxx.md` 的全部内容并发送给 Antigravity（推荐使用 Gemini 3.1 Pro 模型）。等它在 `reports/` 目录生成分析报告后，请通知我，我将审阅并执行下一步修改。”

---

## 8. 示例场景

### 示例 A：Gemini 3.1 Pro 任务（深度架构审查）
- **Task Class**: Architecture Review
- **Scenario**: 检查 `Nexus` BIM 编排层中 `run-claude-task.ps1` 与队列逻辑是否存在死锁。
- **Action**: Antigravity 会深读相关代码，排查上下文状态机，输出风险报告并给出修复方案代码块，由 Codex 接手进行最终 `.ps1` 的修复。

### 示例 B：Gemini 3.1 Flash 任务（批量冗余扫描）
- **Task Class**: Static Asset Scan
- **Scenario**: 扫描 `public/resources/` 目录下所有遗留图纸和重复 Logo，寻找前端从未被引用的废弃文件。
- **Action**: Antigravity 使用 `grep_search` 全局匹配文件引用情况，生成一份表格化清理清单 `asset-cleanup-report.md`，供 Codex 执行删除。
