# openBIMForge — 项目深度技术介绍

> 面试 / 技术评审 / 开题答辩用。本文档覆盖系统架构、核心算法、关键代码片段和设计决策。

---

## 一、项目定位

openBIMForge 是一个**面向建筑信息模型（BIM）的多智能体生成式系统**，核心能力是：

1. 把自然语言 / 语音 / 建筑草图 / 平面图转化为可在 Vectorworks 中执行的 BIM 生成代码
2. 在同一流水线里协同生成**排污 MEP 系统**并导出 IFC4
3. 通过**可切换 LLM + 典型学知识注入 + 质量门控**保证生成精度

**学术关键词**：Generative BIM · Multi-Agent LLM Orchestration · Neurosymbolic MEP Routing · Knowledge-Augmented Code Generation

---

## 二、系统架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Next.js 16 (App Router)                       │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ Chat UI  │  │ ForgeVision  │  │ Settings     │  │ IFC Viewer │  │
│  │ (React)  │  │ Upload/Form  │  │ Agent Config │  │ (Preview)  │  │
│  └────┬─────┘  └──────┬───────┘  └──────────────┘  └────────────┘  │
│       │                │                                             │
│  ┌────▼────────────────▼──────────────────────────────────────────┐  │
│  │              /api/chat (Route Handler)                          │  │
│  │  Stage 0: Clarification Loop (LLM 参数完整度评估)               │  │
│  │  → Route Decision: nexus-synthesis / nexus-visionary            │  │
│  └────────────────────────┬───────────────────────────────────────┘  │
└───────────────────────────┼──────────────────────────────────────────┘
                            │ spawn Python subprocess
┌───────────────────────────▼──────────────────────────────────────────┐
│                    Python Bridge (adapter_entry.py)                    │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              unified_runtime.py (Nexus Pipeline)                │  │
│  │                                                                │  │
│  │  Stage 1: Architect-Agent (Typology 知识注入 + 空间规划)        │  │
│  │  Stage 2: Constructor-Agent (Vectorworks Python 代码合成)       │  │
│  │  Stage 2.5: Checker-Agent (三维度质量审查 + 定向重生成)         │  │
│  │  Stage M: MEP-Engineer (排污专项，可选)                         │  │
│  │  Stage 3: Transit-Payload (JSON 文件交付)                       │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ .json file protocol
┌───────────────────────────▼──────────────────────────────────────────┐
│              Vectorworks 2024+ (Python VM)                            │
│  Stage 4: vectorworks_execute.py → vs.* API → VWX + IFC             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心创新点（面试重点）

### 3.1 可切换 LLM + Agent 模型专业化

**问题**：不同 Agent 的任务性质不同——Architect 需要强推理，Constructor 需要精确代码生成，Checker 只需要轻量判断。用同一个模型是浪费。

**方案**：每个 Agent 可独立指定 provider / model / apiKey / baseUrl，缺省回退到主模型。

```python
# forge_core/build_agent/unified_runtime.py

def _resolve_agent_overrides(llm_config, agent_key):
    """
    从 llm_config.agentOverrides[agent_key] 读取覆盖配置。
    缺失字段回退到主模型配置。
    """
    base = {
        "provider": llm_config.get("provider", ""),
        "modelId": llm_config.get("modelId", ""),
        "baseUrl": llm_config.get("baseUrl", ""),
        "apiKey": llm_config.get("apiKey", ""),
    }
    overrides = (llm_config.get("agentOverrides") or {}).get(agent_key) or {}
    for key in ("provider", "modelId", "baseUrl", "apiKey"):
        value = overrides.get(key)
        if value:
            base[key] = str(value)
    return base

# 使用：
architect_cfg = _resolve_agent_overrides(llm_config, "architect")
agent_po = create_unified_agent(
    provider=architect_cfg["provider"] or provider,
    model_id=architect_cfg["modelId"] or model_id,
    api_key=architect_cfg["apiKey"] or api_key,
    base_url=architect_cfg["baseUrl"] or base_url,
    prompt=po_prompt,
    tool_list=tool_list,
)
```

**推荐搭配**：

| Agent | 推荐模型 | 原因 |
|-------|---------|------|
| Architect | Claude Opus / o3 / DeepSeek R1 | 强空间推理 |
| Constructor | Qwen2.5-Coder / Claude Sonnet | 精确代码生成 |
| Checker | Haiku / 本地 Ollama | 轻量够用 |

---

### 3.2 Typology 知识注入（替代硬编码默认值）

**问题**：LLM 不知道"办公楼标准层高 3.9m、柱网 8.4m、核心筒占比 18%"这些建筑学常识，导致生成的模型参数随机。

**方案**：10 种建筑类型的结构化 JSON 知识包，按 `building_type` 查表注入 prompt。

```json
// forge_core/knowledge/typologies/office.json（节选）
{
    "building_type": "office",
    "design_parameters": {
        "floor_height_m": { "typical": 3.9, "range": [3.3, 4.2] },
        "structural_grid_m": { "typical": 8.4, "options": [7.2, 8.1, 8.4, 9.0] },
        "core_area_ratio": { "typical": 0.18, "range": [0.15, 0.22] },
        "corridor_width_m": { "single_load": 1.5, "double_load": 1.8 }
    },
    "program_zones": [
        { "name": "open_office", "ratio": 0.55, "adjacency": ["corridor"] },
        { "name": "core", "ratio": 0.18, "position": "center" }
    ],
    "default_fallbacks": {
        "floor_height_m": 3.9,
        "storey_count": 6,
        "per_floor_area_m2": 700
    }
}
```

```python
# forge_core/knowledge/loader.py

def build_typology_prompt_hint(building_type):
    """渲染 typology 为 prompt 文本块，直接拼到 Architect/Constructor 提示词后。"""
    typology = load_typology(building_type)
    # 输出格式：
    # [TYPOLOGY KNOWLEDGE: office / 办公楼]
    # Design parameters:
    # - floor_height_m: typical=3.9, range=3.3-4.2
    # - structural_grid_m: typical=8.4, options=7.2,8.1,8.4,9.0
    # ...
    # Usage rules: (1) Always prefer explicit user values over defaults...
```

**效果**：即使用弱模型（Qwen 7B），也能生成参数合理的 BIM 方案。

---

### 3.3 三维度质量评估 + Checker 门控

**问题**：LLM 单次生成不稳定，可能输出"白盒"（只有一个 slab + 4 面墙）。

**方案**：对生成的 Python 代码做**静态分析**，从三个维度打分：

```python
# forge_core/build_agent/quality_evaluator.py

def evaluate_bim_quality(*, code, resources, degradations, requirements):
    metrics = _aggregate_metrics(code)  # 解析 create_wall/slab/space 调用次数
    
    # 维度 1：需求符合度（40%）
    conformance = _score_requirement_conformance(metrics, requirements)
    # → 面积偏差、楼层数匹配、层高匹配
    
    # 维度 2：几何合理性（30%）
    geometry = _score_geometry_validity(metrics, code)
    # → 墙-楼板配套、顶点数合理性
    
    # 维度 3：BIM 语义丰富度（30%）
    richness = _score_bim_richness(metrics, code, resources, degradations)
    # → 楼层/墙/楼板/空间数量，core/corridor 是否存在
    
    overall = conformance * 0.4 + geometry * 0.3 + richness * 0.3
    return {"quality_score": overall, "dimensions": {...}, "next_actions": [...]}
```

**Checker 门控逻辑**：

```python
# forge_core/build_agent/nexus_checker.py

def run_checker_stage(*, code, requirements, agent_coder, threshold=80, ...):
    report = evaluate_bim_quality(code=code, requirements=requirements, ...)
    
    if report["quality_score"] >= threshold:
        return {"code": code, "did_rewrite": False}  # 直接通过
    
    # 分数不足 → 生成结构化反馈 → Constructor 重生成一次
    feedback = _build_rewrite_instruction(report, requirements)
    _, revised_code = agent_coder.chat(feedback, ...)
    
    revised_report = evaluate_bim_quality(code=revised_code, ...)
    # 只有新版本更好才接受，否则回退
    accepted = revised_report["quality_score"] >= report["quality_score"]
    return {"code": revised_code if accepted else code, "did_rewrite": accepted}
```

**关键设计**：最多只重写 1 次，避免无限循环。

---

### 3.4 MEP 排污系统生成（Neurosymbolic）

**问题**：纯 LLM 无法精确计算管径、坡度、路径避让。纯算法不懂"哪里是卫生间"。

**方案**：LLM 定策略（器具放哪里），算法做约束求解（管怎么走）。

#### Stage B — 器具定位（规则式）

```python
# forge_core/mep_agent/fixture_placer.py

def _place_single_fixture(room, fixture_type, index, total_of_type):
    """规则式定位：马桶贴远门墙、洗手盆贴近门墙、地漏在中心。"""
    if fixture_type in {"toilet", "squat_toilet"}:
        target_edge = _edge_farthest_from_point(room.polygon, door_point)
    elif fixture_type == "wash_basin":
        target_edge = _edge_nearest_to_point(room.polygon, door_point)
    elif fixture_type == "floor_drain":
        return room.centroid(), 0.0, room.centroid()
    
    position, rotation = _place_along_edge(target_edge, fraction, inward_offset, centroid)
    return position, rotation, connection_point
```

#### Stage C — 立管聚类（自适应 K-means）

```python
# forge_core/mep_agent/stack_planner.py

def plan_stacks(building, fixtures, max_cluster_radius_mm=6000.0):
    """用自适应 K-means 决定立管数量和位置。"""
    points = [f.connection_point for f in fixtures]
    centroids, _ = _adaptive_cluster(points, max_cluster_radius_mm)
    # 对齐到最近的管井（Shaft）
    aligned = [_snap_to_shaft(c, all_shafts) for c in centroids]
    return [Stack(position=c, ...) for c in aligned]
```

#### Stage D — A\* 约束路径规划 + Merge-Tree 合流

```python
# forge_core/mep_agent/pipe_router.py

def route_branches(building, fixtures, stacks, ...):
    """用 Prim MST 建合流拓扑，再用 A* 物化每条边。"""
    for stack in stacks:
        tree = build_merge_tree(stack, fixtures_by_id)
        annotate_cumulative_du(tree, fixtures_by_id)  # 累积排水当量
        
        for child, parent in tree.iter_edges():
            path = _a_star(start_cell, goal_cell, search_mask)
            # 坡度：高端在器具，低端在立管
            # 约束：不穿梁（Obstacle polygon 膨胀后标记为不可走）
            pipes.append(PipeSegment(
                kind="branch" if child.fixture_id else "trunk",
                diameter_mm=0.0,  # Stage E 按累积 DU 查表填充
                slope_pct=actual_slope_pct,
                fixture_ids=downstream_fixtures,
            ))
```

#### Stage E — GB 50015 管径查表

```python
# forge_core/mep_agent/sizing.py

def size_branches(pipes, fixtures):
    """按每段管的下游累积 DU 查 GB 50015 表定径。"""
    for seg in pipes:
        du = sum(fixture_du[fid] for fid in seg.fixture_ids)
        table_diameter = _pick_diameter(du, "soil_branch")
        # 查表：DU≤4→DN50, ≤10→DN75, ≤30→DN100, ≤100→DN150, else→DN200
        seg.diameter_mm = max(seg.diameter_mm, table_diameter, outlet_floor)
```

#### IFC4 导出（零依赖）

```python
# forge_core/mep_agent/ifc_exporter.py

def export_mep_to_ifc(building, plan, output_path):
    """手写 IFC4 SPF 格式，不依赖 ifcopenshell。"""
    writer = _IfcWriter(plan.project_name)
    # 每个管段 = IfcPipeSegment + IfcExtrudedAreaSolid（圆截面拉伸）
    for seg in plan.pipes:
        axis, ref, length = _compute_pipe_axis(seg.start, seg.end)
        # 圆形截面 profile
        profile = writer.entity("IFCCIRCLEPROFILEDEF", ...)
        # 沿管轴拉伸
        solid = writer.entity("IFCEXTRUDEDAREASOLID", ...)
        # 定位
        writer.entity("IFCPIPESEGMENT", ...)
    writer.write(output_path)
```

---

### 3.5 CAD-First 高精度分支（借鉴 GenCAD）

**问题**：纯文字描述无法传达复杂几何（L 形、退台、曲面）。

**方案**：用户上传图片 → GenCAD 引擎生成 CAD 向量序列 → 提取几何特征 → 注入 Constructor prompt。

```python
# forge_core/build_agent/unified_runtime.py

def _read_cad_vector_hint(cad_vector_path):
    """解析 GenCAD 输出的 cad_vector.json，提取几何特征。"""
    # GenCAD 向量格式：[[command, x, y, ...], ...]
    # command 0=line, 1=arc, 4=profile_start, 5=extrude
    
    complexity_score = min(100,
        straight_count * 2 + curve_count * 4 +
        extrusion_count * 8 + profile_count * 5
    )
    
    # 空间语义分类
    if profile_count >= 3 or extrusion_count >= 3:
        spatial_reading = "multi-volume stepped massing"
    elif curve_count >= 2:
        spatial_reading = "curved or rounded footprint reference"
    elif straight_count >= 4:
        spatial_reading = "orthogonal footprint reference"
    
    return {
        "complexity_score": complexity_score,
        "spatial_reading": spatial_reading,
        "raw_coordinates": raw_coordinates[:100],
        "normalized_width": ...,
        "normalized_depth": ...,
    }
```

当 `complexity_score > 10` 时触发 CAD-First 模式：

```python
if _get_forgevision_complexity_score(context_hint) > 10:
    cad_instruction = (
        "[CRITICAL: VECTOR-DRIVEN SYNTHESIS]\n"
        "You MUST use the provided [CAD_COORDINATES] to define building "
        "footprints and wall segments. DO NOT rely on the STL mesh."
    )
    constructor_input = cad_instruction + constructor_input
```

---

### 3.6 前端 Claude Code 风格执行流

每个 Nexus 阶段在前端是一个**独立可折叠的 CollapsibleStageRow**：

```tsx
// components/chat-message-display.tsx

function CollapsibleStageRow({ stage, defaultOpen }) {
    // 运行中/失败 → 默认展开；完成 → 默认折叠
    const [open, setOpen] = useState(
        defaultOpen ?? (stage.status === "running" || stage.status === "failed")
    )
    return (
        <div>
            <button onClick={() => setOpen(!open)}>
                <StatusDot status={stage.status} />  {/* ✓绿 / ✗红 / 🔄蓝 */}
                <span>{icon} {label}</span>
                <span>{duration}s</span>
                {open ? <ChevronDown /> : <ChevronRight />}
            </button>
            {open && <div className="border-l-2">{stage.detail}</div>}
        </div>
    )
}
```

Quality 评分面板：

```tsx
function QualityPanel({ quality }) {
    // 三个维度并排 tile，按分档上色（≥85绿 / 60-85黄 / <60红）
    return (
        <div className="grid grid-cols-3 gap-2">
            <DimensionTile label="需求符合度" score={conformance.score} />
            <DimensionTile label="几何合理性" score={geometry.score} />
            <DimensionTile label="BIM 语义丰富度" score={richness.score} />
        </div>
    )
}
```

---

## 四、MEP Benchmark 评测

```bash
uv run -m benchmark.run_benchmark --format markdown
```

| Case | Fixtures | Stacks | 管段 | 管长 | Quality |
|------|---------|--------|------|------|---------|
| 6 层办公楼 | 51 | 1 | 54 | 52.50 m | 100/100 |
| 单层 4 户住宅 | 20 | 2 | 28 | 56.29 m | 100/100 |
| 4 层教学楼 | 55 | 2 | 63 | 84.75 m | 100/100 |

评测四维度：`connectivity`（连通率）· `slope`（坡度合规）· `sizing`（管径合规）· `code_compliance`（GB 50015 通气/清扫口）。

---

## 五、测试覆盖

```bash
uv run pytest tests -v
# 21 passed in 0.19s
```

覆盖：
- Fixture Placer：器具数量 / 位置在房间内 / 模板匹配
- Stack Planner：聚类数量 / 全覆盖 / 高度跨度
- Pipe Router：全连通 / 坡度合规 / 立管垂直 / 梁避让
- Sizing：GB 50015 查表正确性
- IFC Exporter：IFCPIPESEGMENT 数量 round-trip
- Merge Tree：叶节点覆盖 / 根节点可达 / 累积 DU 单调递增
- Quality：综合评分合理性

---

## 六、技术栈一览

| 层 | 技术 |
|----|------|
| 前端 | Next.js 16 · React 19 · Tailwind v4 · Radix UI · Vercel AI SDK v6 |
| 后端编排 | Next.js Route Handlers · Node.js · Python Bridge (child_process) |
| LLM 适配 | 20+ 提供商统一接口 · SSRF 防护 · API Key 负载均衡 |
| Python Agent | OpenAI SDK · Anthropic SDK · Google GenAI · httpx |
| MEP 算法 | A\* · Prim MST · K-means · Douglas-Peucker（规划中） |
| BIM 运行时 | Vectorworks 2024+ · vs.* Python SDK · IFC4 SPF |
| 可观测性 | Langfuse · OpenTelemetry |
| 包管理 | uv (Python) · npm (Node) |
| 部署 | Cloudflare Workers · Vercel · Docker · EdgeOne |

---

## 七、项目规模

- TypeScript / TSX：~15,000 行
- Python：~5,000 行
- 单元测试：21 个
- Benchmark cases：3 个（可扩展）
- Typology 知识包：10 种建筑类型
- 支持 LLM 提供商：20+
- IFC 导出：零外部依赖

---

## 八、面试常见问题预答

**Q: 为什么不直接让 LLM 生成 IFC？**
A: IFC 是严格的 STEP 格式，LLM 直接生成会有大量语法错误。我们让 LLM 生成 Vectorworks Python 代码（高层 API），由 VM 执行后导出 IFC，保证格式合规。

**Q: MEP 为什么不用纯 LLM？**
A: 管径计算是查表（GB 50015），坡度是物理约束（≥2%），路径规划是 NP-hard 问题。LLM 擅长"决定马桶放哪里"（语义），不擅长"算管径 DN100 还是 DN150"（精确计算）。所以我们用 Neurosymbolic 方案：LLM 定策略，算法做求解。

**Q: Typology 知识包和 RAG 有什么区别？**
A: Typology 是确定性查表（key=building_type），不是语义检索。因为"办公楼层高多少"是一个确定性问题，不需要 embedding 相似度搜索。RAG 适合"防火规范第几条怎么说"这种非结构化长文本检索，我们规划在后续版本加入。

**Q: Merge Tree 相比独立路由有什么优势？**
A: 独立路由每个器具一根管到立管，管段数 143；Merge Tree 合流后管段数 57（减少 60%），且合流后的 trunk 管径按累积 DU 放大，符合 GB 50015 规范。

**Q: 质量评估为什么是静态分析而不是跑 Solibri？**
A: 静态分析可以在 dry-run 模式下运行（不需要 Vectorworks VM），适合 CI 和 benchmark。Solibri 检查是 Stage 4 之后的事，两者互补。

---

*文档版本：2026-05-11 · 对应 commit: 684f856*
