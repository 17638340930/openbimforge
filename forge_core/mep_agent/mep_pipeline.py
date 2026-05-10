"""
Top-level orchestrator for the MEP agent.

Keeping the stages decoupled in their own modules makes each easy to test
in isolation; this file wires them together in the canonical order.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any, Callable, Dict, Optional

from .fixture_placer import place_fixtures
from .ifc_exporter import export_mep_to_ifc
from .pipe_router import build_stack_segments, route_branches
from .quality import evaluate_mep_quality
from .schema import BuildingPlan, MepPlan, Storey
from .sizing import insert_cleanouts, size_branches, size_stack_segments, size_stacks
from .stack_planner import plan_stacks
from .vectorworks_script_gen import generate_vectorworks_script


StageCallback = Callable[[Dict[str, Any]], None]


def _emit_stage(callback: Optional[StageCallback], **event: Any) -> None:
    if callback is None:
        return
    callback(event)


def _load_building_plan(source: Any) -> BuildingPlan:
    if isinstance(source, BuildingPlan):
        return source
    if isinstance(source, str):
        with open(source, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    elif isinstance(source, dict):
        data = source
    else:
        raise TypeError(f"Unsupported building plan source type: {type(source)!r}")

    from .schema import Fixture, Obstacle, Room, Shaft  # local import to avoid cycles

    storeys = []
    for s in data.get("storeys", []):
        storey = Storey(
            id=s["id"],
            index=int(s.get("index", 0)),
            elevation_mm=float(s.get("elevation_mm", 0.0)),
            height_mm=float(s.get("height_mm", 3000.0)),
            outline=[tuple(pt) for pt in s.get("outline", [])],
            rooms=[
                Room(
                    id=r["id"],
                    storey_id=s["id"],
                    type=r["type"],
                    polygon=[tuple(pt) for pt in r["polygon"]],
                    door=tuple(r["door"]) if r.get("door") else None,
                    label_zh=r.get("label_zh"),
                )
                for r in s.get("rooms", [])
            ],
            shafts=[
                Shaft(
                    id=sh["id"],
                    polygon=[tuple(pt) for pt in sh["polygon"]],
                    label_zh=sh.get("label_zh"),
                )
                for sh in s.get("shafts", [])
            ],
            obstacles=[
                Obstacle(
                    id=ob["id"],
                    polygon=[tuple(pt) for pt in ob["polygon"]],
                    kind=ob.get("kind", "beam"),
                    z_min_mm=(float(ob["z_min_mm"]) if ob.get("z_min_mm") is not None else None),
                    z_max_mm=(float(ob["z_max_mm"]) if ob.get("z_max_mm") is not None else None),
                    label_zh=ob.get("label_zh"),
                )
                for ob in s.get("obstacles", [])
            ],
        )
        storeys.append(storey)

    return BuildingPlan(
        project_name=data.get("project_name", "openBIMForge-MEP"),
        storeys=storeys,
        ceiling_void_mm=float(data.get("ceiling_void_mm", 500.0)),
        ground_elevation_mm=float(data.get("ground_elevation_mm", 0.0)),
        roof_elevation_mm=(
            float(data["roof_elevation_mm"]) if data.get("roof_elevation_mm") is not None else None
        ),
    )


def run_mep_pipeline(
    source: Any,
    *,
    output_dir: Optional[str] = None,
    write_ifc: bool = False,
    write_script: bool = False,
    on_stage: Optional[StageCallback] = None,
) -> Dict[str, Any]:
    """Runs all MEP stages and returns a dict with the plan and optional files.

    Parameters
    ----------
    source:
        Either a `BuildingPlan`, a dict with the serialised plan, or a path
        to a JSON file on disk.
    output_dir:
        If provided, per-stage artefacts (IFC / Python script) are written
        there. The directory is created if missing.
    write_ifc, write_script:
        Toggle the respective exporters. They only run when ``output_dir``
        is set.
    on_stage:
        Optional callback that receives a dict per stage, mirroring the
        ``emit_stage_event`` contract used by the Nexus pipeline.
    """
    building = _load_building_plan(source)
    plan = MepPlan(project_name=building.project_name)

    _emit_stage(on_stage, id="mep_fixtures", status="running", label="MEP-Fixture-Placement")
    plan.fixtures = place_fixtures(building)
    _emit_stage(
        on_stage,
        id="mep_fixtures",
        status="completed",
        label="MEP-Fixture-Placement",
        detail=f"{len(plan.fixtures)} fixtures placed",
    )

    _emit_stage(on_stage, id="mep_stacks", status="running", label="MEP-Stack-Planning")
    plan.stacks = plan_stacks(building, plan.fixtures)
    _emit_stage(
        on_stage,
        id="mep_stacks",
        status="completed",
        label="MEP-Stack-Planning",
        detail=f"{len(plan.stacks)} stacks planned",
    )

    _emit_stage(on_stage, id="mep_routing", status="running", label="MEP-Pipe-Routing")
    branch_segments, warnings = route_branches(building, plan.fixtures, plan.stacks)
    plan.pipes.extend(branch_segments)
    plan.pipes.extend(build_stack_segments(building, plan.stacks))
    plan.warnings.extend(warnings)
    _emit_stage(
        on_stage,
        id="mep_routing",
        status="completed" if not warnings else "completed_with_warnings",
        label="MEP-Pipe-Routing",
        detail=f"{len(plan.pipes)} segments ({len(warnings)} warnings)",
    )

    _emit_stage(on_stage, id="mep_sizing", status="running", label="MEP-Sizing-and-Venting")
    size_stacks(plan.stacks)
    size_stack_segments(plan.pipes, plan.stacks)
    size_branches(plan.pipes, plan.fixtures)
    plan.pipes.extend(insert_cleanouts(plan.pipes))
    _emit_stage(
        on_stage,
        id="mep_sizing",
        status="completed",
        label="MEP-Sizing-and-Venting",
        detail=f"{sum(1 for s in plan.pipes if s.kind == 'cleanout')} cleanouts inserted",
    )

    quality = evaluate_mep_quality(plan)
    plan.metrics = quality.get("metrics", {})

    artefacts: Dict[str, str] = {}
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        if write_ifc:
            ifc_path = os.path.join(output_dir, f"{plan.project_name}.ifc")
            export_mep_to_ifc(building, plan, ifc_path)
            artefacts["ifc_path"] = ifc_path
        if write_script:
            script_path = os.path.join(output_dir, f"{plan.project_name}.vw.py")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(generate_vectorworks_script(plan))
            artefacts["script_path"] = script_path
        plan_path = os.path.join(output_dir, f"{plan.project_name}.mep.json")
        with open(plan_path, "w", encoding="utf-8") as handle:
            json.dump(plan.serialise(), handle, ensure_ascii=False, indent=2)
        artefacts["plan_path"] = plan_path

    return {
        "plan": plan,
        "quality": quality,
        "artefacts": artefacts,
    }
