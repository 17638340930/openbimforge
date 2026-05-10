# openBIMForge MEP Benchmark Suite

本目录是 openBIMForge MEP agent 的**定量评测集**。目的：

1. 量化"典型学知识包 + Merge-Tree 路由"对生成质量的影响；
2. 为论文提供可复现的表格和图表数据；
3. 给后续算法迭代一个不回退的 baseline。

## 目录结构

```
benchmark/
  cases/*.json          每个 case 一个 BuildingPlan（与 mep_agent examples 格式一致）
  expected/             每个 case 可选的人工参考答案（用于人工评分）
  run_benchmark.py      跑遍所有 case，输出 JSON + Markdown 对比表
  README.md             本文件
```

## 如何跑

```bash
uv run -m benchmark.run_benchmark \
    --output forge_runtime/benchmark \
    --format markdown
```

结果会落地到 `forge_runtime/benchmark/`：
- `results.json`：每个 case 的完整 `MepPlan` + `quality` 报告
- `summary.md`：可直接粘进论文的 Markdown 表格
- `summary.csv`：Excel / Pandas 兼容格式

## 指标说明

| 指标 | 出处 | 论文语义 |
|------|-----|---------|
| `connectivity.score` | `quality.evaluate_mep_quality` | 连通率 —— 每个器具都能接入立管 |
| `slope.score` | 同上 | 坡度合规率 |
| `sizing.score` | 同上 | 管径合规率 |
| `code_compliance.score` | 同上 | 通气 + 清扫口完整度 |
| `quality_score` | 同上 | 综合加权得分 |
| `pipe_count` | `MepPlan` | 管段总数 |
| `trunk_segment_count` | `MepPlan` | 合流段数量（Merge-Tree 改造的直接产物） |
| `total_pipe_length_m` | `MepPlan` | 管材总长度 |

## 建议的 ablation 实验

论文里建议跑 3 组对比：

1. **Baseline**: 没有 typology 注入，没有 Merge Tree（需要临时关闭两个开关）
2. **+Typology**: 开 typology 注入
3. **+Typology + MergeTree**: 当前默认状态（本 benchmark 默认跑这个）

第 1 / 2 组可以通过环境变量关闭对应特性实现，再次跑本 benchmark 即可。
