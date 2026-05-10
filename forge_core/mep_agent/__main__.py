"""
CLI entry point for running the MEP agent standalone.

Example
-------

    python -m forge_core.mep_agent \
        --input forge_core/mep_agent/examples/office_6f_demo.json \
        --output forge_runtime/mep_out \
        --ifc --script
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from .mep_pipeline import run_mep_pipeline


def _stage_logger(event: Dict[str, Any]) -> None:
    detail = event.get("detail", "")
    print(f"[{event.get('status', 'info'):<24}] {event.get('label', event.get('id', 'stage'))} {detail}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the openBIMForge MEP agent.")
    parser.add_argument("--input", required=True, help="Path to a BuildingPlan JSON file.")
    parser.add_argument("--output", required=True, help="Directory to write artefacts into.")
    parser.add_argument("--ifc", action="store_true", help="Also emit an IFC4 file.")
    parser.add_argument("--script", action="store_true", help="Also emit a Vectorworks Python script.")
    args = parser.parse_args(argv)

    result = run_mep_pipeline(
        args.input,
        output_dir=args.output,
        write_ifc=args.ifc,
        write_script=args.script,
        on_stage=_stage_logger,
    )
    plan = result["plan"]
    quality = result["quality"]
    artefacts = result["artefacts"]

    print()
    print("=" * 60)
    print(f"MEP plan for {plan.project_name}")
    print(f"  fixtures       : {len(plan.fixtures)}")
    print(f"  stacks         : {len(plan.stacks)}")
    print(f"  pipe segments  : {len(plan.pipes)}")
    print(f"  warnings       : {len(plan.warnings)}")
    print(f"  quality score  : {quality['quality_score']}/100 ({quality['build_status']})")
    for key, value in artefacts.items():
        print(f"  {key:<14} : {value}")
    for warning in plan.warnings[:10]:
        print(f"  WARN: {warning}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
