# openBIMForge 文档清理计划

本文档记录当前文档资产状态和清理建议。它不直接删除文件，用于后续人工确认。

## 1. 当前发现

### 1.1 README.md

状态：需要重写。

问题：

- 当前 `README.md` 出现明显编码损坏。
- 内容混合了旧 Text2BIM、ForgeVision 早期设想、当前 Nexus 架构，难以作为入口文档。
- 建议用简短 README 替换，主链路细节链接到 `docs/nexus_full_pipeline_map.md`。

建议：

- 保留项目简介。
- 保留快速启动。
- 保留核心链路图的链接。
- 不再在 README 中展开长篇架构细节。

### 1.2 handover_brief.md

状态：当前 `openBIMForge` 根目录未发现。

说明：

- 用户曾提到路径 `D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge\handover_brief.md`。
- 本次盘点时该文件不存在。
- 如果旧文件在上级目录或其他副本中，应迁移为 `docs/handover_current.md`，并以 `docs/nexus_full_pipeline_map.md` 为准更新。

### 1.3 docs/FULL_CHAIN_TEST.md

状态：建议保留，但需要后续对照当前链路更新。

用途：

- 放端到端测试步骤。
- 应补充 CAD-First、pending 文件、Vectorworks VM 回写的验收点。

### 1.4 docs/VECTORWORKS_PLUGIN_INSTALL.md

状态：建议保留。

用途：

- Vectorworks 插件安装说明。
- Stage4 物理链路依赖它。

### 1.5 docs/AGENTS.md

状态：需要重写或删除。

问题：

- 文件内容已严重乱码。
- 如果作为 Agent 指令文件，会造成误导。

建议：

- 新建清晰版 `docs/AGENTS.md` 或删除。
- 如果保留，只写文档目录维护规则，不写过期架构。

### 1.6 .ai_agents/reports/

状态：建议归档，不建议作为正式文档。

用途：

- 外部 Agent / Gemini / Claude 的审计报告。
- 可作为过程记录，但不能替代当前源码事实。

建议：

- 保留最近有效报告。
- 旧烟测、空报告、重复审计报告可移入 `.ai_agents/reports/archive/`。
- 论文或交接只引用最终整理后的 `docs/*.md`。

## 2. 建议文档结构

```text
docs/
├─ nexus_full_pipeline_map.md        # 当前权威全链路文档
├─ documentation_cleanup_plan.md     # 文档清理计划
├─ FULL_CHAIN_TEST.md                # 端到端测试计划
├─ VECTORWORKS_PLUGIN_INSTALL.md     # Vectorworks 安装与桥接
├─ handover_current.md               # 后续可新增：交接摘要
├─ thesis_roadmap.md                 # 后续可新增：论文路线图
└─ legacy/
   └─ text2bim_legacy_notes.md       # 后续可新增：旧链路说明
```

## 3. 建议替换 README.md 的结构

```text
# openBIMForge

## 项目简介
一句话说明：Nexus 多 Agent + ForgeVision + Vectorworks VM 的图文生 BIM 系统。

## 当前已实现
- Text-to-BIM
- ForgeVision-Form
- CAD-First
- Vectorworks Stage4

## 当前未完成
- ForgeVision-Layout
- 论文实验指标体系

## 快速启动
- npm / Python / env / Vectorworks

## 核心文档
- docs/nexus_full_pipeline_map.md
- docs/FULL_CHAIN_TEST.md
- docs/VECTORWORKS_PLUGIN_INSTALL.md
```

## 4. 清理顺序建议

1. 先确认 `docs/nexus_full_pipeline_map.md` 内容准确。
2. 重写 `README.md`。
3. 重写或删除 `docs/AGENTS.md`。
4. 更新 `docs/FULL_CHAIN_TEST.md`。
5. 将 `.ai_agents/reports/` 中过期报告归档。
6. 如有旧 `handover_brief.md`，迁移成 `docs/handover_current.md`。

## 5. 不建议删除的内容

- `docs/VECTORWORKS_PLUGIN_INSTALL.md`
- `docs/FULL_CHAIN_TEST.md`
- `.ai_agents/reports/硕士论文路线图-北科大.md`
- `.ai_agents/reports/GitHub项目展示冲刺指南.md`

这些文件可能对论文、展示或部署仍有参考价值。
