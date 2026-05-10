"""
MEP benchmark runner.

Loads every ``benchmark/cases/case_*.json`` file, runs the MEP pipeline
against its ``plan`` block, and produces a summary table in JSON / CSV /
Markdown so the results can be dropped straight into a paper.

Usage
-----

    uv run -m benchmark.run_benchmark \
        --output forge_runtime/benchmark \
        --format markdown
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forge_core.mep_agent import MepPlan, run_mep_pipeline
from forge_core.mep_agent.schema import segment_length_3d


CASES_DIR = Path(__file__).resolve().parent / "cases"


def _case_files() -> List[Path]:
    return sorted(CASES_DIR.glob("case_*.json"))


def _aggregate_metrics(plan: MepPlan, quality: Dict[str, Any]) -> Dict[str, Any]:
    trunk_count = sum(1 for seg in plan.pipes if seg.kind == "trunk")
    branch_count = sum(1 for seg in plan.pipes if seg.kind == "branch")
    stack_count = sum(1 for seg in plan.pipes if seg.kind == "stack")
    vent_count = sum(1 for seg in plan.pipes if seg.kind == "vent")
    cleanout_count = sum(1 for seg in plan.pipes if seg.kind == "cleanout")
    total_length_mm = sum(segment_length_3d(s.start, s.end) for s in plan.pipes)

    dims = quality.get("dimensions") or {}
    return {
        "project_name": plan.project_name,
        "fixture_count": len(plan.fixtures),
        "stack_count": len(plan.stacks),
        "branch_count": branch_count,
        "trunk_count": trunk_count,
        "vertical_stack_count": stack_count,
        "vent_count": vent_count,
        "cleanout_count": cleanout_count,
        "total_pipe_length_m": round(total_length_mm / 1000.0, 2),
        "quality_score": quality.get("quality_score"),
        "build_status": quality.get("build_status"),
        "connectivity": (dims.get("connectivity") or {}).get("score"),
        "slope": (dims.get("slope") or {}).get("score"),
        "sizing": (dims.get("sizing") or {}).get("score"),
        "code_compliance": (dims.get("code_compliance") or {}).get("score"),
        "warnings": list(plan.warnings),
    }


def _render_markdown(rows: List[Dict[str, Any]]) -> str:
    headers = [
        "case_id",
        "fixtures",
        "stacks",
        "branches",
        "trunks",
        "cleanouts",
        "pipe_m",
        "quality",
        "conn",
        "slope",
        "size",
        "code",
    ]
    lines = [
        "# MEP Benchmark Summary",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("case_id", "")),
                    str(row.get("fixture_count", "")),
                    str(row.get("stack_count", "")),
                    str(row.get("branch_count", "")),
                    str(row.get("trunk_count", "")),
                    str(row.get("cleanout_count", "")),
                    f"{row.get('total_pipe_length_m', 0):.2f}",
                    str(row.get("quality_score", "")),
                    str(row.get("connectivity", "")),
                    str(row.get("slope", "")),
                    str(row.get("sizing", "")),
                    str(row.get("code_compliance", "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _render_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    field_names = [
        "case_id",
        "project_name",
        "fixture_count",
        "stack_count",
        "branch_count",
        "trunk_count",
        "vertical_stack_count",
        "vent_count",
        "cleanout_count",
        "total_pipe_length_m",
        "quality_score",
        "build_status",
        "connectivity",
        "slope",
        "sizing",
        "code_compliance",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in field_names})


def run_all(output_dir: Path, emit_format: str) -> List[Dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []
    for case_path in _case_files():
        with case_path.open("r", encoding="utf-8") as handle:
            case = json.load(handle)

        plan_block = case.get("plan") or {}
        pipeline_result = run_mep_pipeline(
            plan_block,
            output_dir=str(output_dir / case["case_id"]),
            write_ifc=True,
            write_script=False,
        )
        plan = pipeline_result["plan"]
        quality = pipeline_result["quality"]

        metrics = _aggregate_metrics(plan, quality)
        metrics["case_id"] = case["case_id"]
        metrics["description"] = case.get("description", "")
        metrics["building_type"] = case.get("building_type", "")
        results.append(metrics)

        print(
            f"[{metrics['quality_score']:>3}/100] {metrics['case_id']:<30} "
            f"fixtures={metrics['fixture_count']:>3} "
            f"stacks={metrics['stack_count']} "
            f"trunks={metrics['trunk_count']:>3} "
            f"branches={metrics['branch_count']:>3} "
            f"pipe={metrics['total_pipe_length_m']:>6.2f}m"
        )

    (output_dir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _render_csv(results, output_dir / "summary.csv")
    if emit_format in {"markdown", "md"}:
        (output_dir / "summary.md").write_text(_render_markdown(results), encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the openBIMForge MEP benchmark")
    parser.add_argument(
        "--output",
        default="forge_runtime/benchmark",
        help="Directory to write per-case IFCs and summary tables into.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "csv", "markdown", "md"),
        default="markdown",
        help="Additional summary format to emit (results.json and summary.csv are always written).",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    results = run_all(output_dir, emit_format=args.format)

    print()
    print("=" * 60)
    print(f"Benchmark complete. {len(results)} case(s) processed.")
    print(f"Summary: {output_dir / 'summary.md' if args.format in {'markdown', 'md'} else (output_dir / 'summary.csv')}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
