# MEP Agent — Sanitary Drainage

专项生成排污系统的多阶段 Agent，作为 openBIMForge Nexus 的第二个「领域专家智能体」。

## 设计定位

| 阶段 | 中文名 | 职责 | 核心方法 |
|------|--------|------|----------|
| Stage A | 数据富化 | 房间 → 器具需求映射 | Typology + `mep_fixtures.json` |
| Stage B | Fixture Placer | 器具定位 | 规则式（LLM 可扩展） |
| Stage C | Stack Planner | 立管规划 | 自适应 K-means 聚类 |
| Stage D | Pipe Router | 横管布线 | A\* + 转弯惩罚 + 房间避让 |
| Stage E | Sizing + Venting | 管径/通气/清扫口 | GB 50015 查表 + 规则 |

## 快速运行

```
python -m forge_core.mep_agent \
    --input forge_core/mep_agent/examples/office_6f_demo.json \
    --output forge_runtime/mep_out \
    --ifc --script
```

产出：

- `demo_office_6f.mep.json`：结构化 MEP 方案
- `demo_office_6f.ifc`：IFC4，可直接拖进 Solibri / ifc.js / BIMvision
- `demo_office_6f.vw.py`：Vectorworks Python 脚本（调试期使用）

## 质量评估

`evaluate_mep_quality(plan)` 输出四维评分：

- `connectivity`：器具到立管的连通率
- `slope`：横管坡度是否在 1.5%–5% 区间
- `sizing`：管径是否 ≥ 器具出水口
- `code_compliance`：通气立管完整度、清扫口间距

## 与建筑 Agent 的边界

建筑 Agent 负责输出 `BuildingPlan`（楼层 / 房间 / 管井 / 门位置）。
MEP Agent 接收 `BuildingPlan` 作为输入，不反向修改建筑结构。
后续要做给水、HVAC 时，各自作为独立子 Agent 共享同一个 `BuildingPlan`。

## 参考规范

- 《建筑给水排水设计标准 GB 50015-2019》—— 表 4.4.5、附录 A、第 4.5 节
- ISO 4.5.5：排水立管当量表
