"""
Quality evaluator for MEP plans.

Runs a series of static checks on a `MepPlan` and produces a structured
report mirroring the BIM quality evaluator (`forge_core.build_agent.
quality_evaluator`) so the frontend ExecutionCard can reuse the same
rendering.

Dimensions:

- ``connectivity``: do all fixtures drain to a stack?
- ``slope``: is every branch pipe's slope inside [1.5%, 5%]?
- ``sizing``: is each diameter >= the fixture outlet diameter?
- ``code_compliance``: is there at least one vent per stack? cleanouts
  present when branches exceed the configured maximum spacing?
"""

from __future__ import annotations

from typing import Any, Dict, List

from .schema import Fixture, MepPlan, PipeSegment, Stack, segment_length_3d


def _score_connectivity(plan: MepPlan) -> Dict[str, Any]:
    fixtures_with_stack = 0
    drainage_kinds = {"branch", "trunk"}
    for fix in plan.fixtures:
        if any(
            seg.kind in drainage_kinds and fix.id in seg.fixture_ids
            for seg in plan.pipes
        ):
            fixtures_with_stack += 1
    total = len(plan.fixtures) or 1
    coverage = fixtures_with_stack / total
    score = int(100 * coverage)
    return {
        "fixtures_total": total,
        "fixtures_routed": fixtures_with_stack,
        "coverage_pct": round(coverage * 100, 1),
        "score": score,
    }


def _score_slope(plan: MepPlan) -> Dict[str, Any]:
    branches = [p for p in plan.pipes if p.kind in {"branch", "trunk"}]
    if not branches:
        return {"score": 100, "checked": 0}
    ok = 0
    for seg in branches:
        if 1.5 <= seg.slope_pct <= 5.0:
            ok += 1
    score = int(100 * ok / len(branches))
    return {
        "checked": len(branches),
        "within_range": ok,
        "score": score,
    }


def _score_sizing(plan: MepPlan) -> Dict[str, Any]:
    fixture_lookup = {f.id: f for f in plan.fixtures}
    offenders: List[str] = []
    drainage_kinds = {"branch", "trunk"}
    for seg in plan.pipes:
        if seg.kind not in drainage_kinds:
            continue
        for fid in seg.fixture_ids:
            fix = fixture_lookup.get(fid)
            if fix and seg.diameter_mm < fix.drain_diameter_mm - 0.1:
                offenders.append(seg.id)
                break
    total = sum(1 for p in plan.pipes if p.kind in drainage_kinds) or 1
    ok = total - len(offenders)
    score = int(100 * ok / total)
    return {
        "checked": total,
        "offending_segments": offenders[:20],
        "score": score,
    }


def _score_code_compliance(plan: MepPlan) -> Dict[str, Any]:
    stack_ids = {s.id for s in plan.stacks}
    vents = {
        seg.stack_id
        for seg in plan.pipes
        if seg.kind == "vent" and seg.stack_id is not None
    }
    missing_vents = sorted(stack_ids - vents)
    has_cleanouts = any(seg.kind == "cleanout" for seg in plan.pipes)
    penalty = 0
    if missing_vents:
        penalty += 15 * min(len(missing_vents), 4)
    if not has_cleanouts and _max_branch_length(plan) > 15_000.0:
        penalty += 10
    score = max(0, 100 - penalty)
    return {
        "stack_count": len(stack_ids),
        "vented_stacks": len(vents),
        "missing_vent_stack_ids": missing_vents,
        "has_cleanouts": has_cleanouts,
        "score": score,
    }


def _max_branch_length(plan: MepPlan) -> float:
    total_by_stack: Dict[str, float] = {}
    for seg in plan.pipes:
        if seg.kind in {"branch", "trunk"} and seg.stack_id:
            total_by_stack[seg.stack_id] = total_by_stack.get(seg.stack_id, 0.0) + segment_length_3d(seg.start, seg.end)
    return max(total_by_stack.values(), default=0.0)


def evaluate_mep_quality(plan: MepPlan) -> Dict[str, Any]:
    conn = _score_connectivity(plan)
    slope = _score_slope(plan)
    sizing = _score_sizing(plan)
    code = _score_code_compliance(plan)

    overall = round(
        conn["score"] * 0.35
        + slope["score"] * 0.2
        + sizing["score"] * 0.2
        + code["score"] * 0.25
    )
    overall = max(0, min(100, int(overall)))
    if overall >= 85:
        status = "success"
    elif overall >= 60:
        status = "partial_success"
    else:
        status = "needs_revision"

    next_actions: List[str] = []
    if conn["score"] < 100:
        next_actions.append(
            "Re-run fixture placement or stack planner; some fixtures are unrouted."
        )
    if slope["score"] < 90:
        next_actions.append(
            "Inspect branches whose planar length exceeds available ceiling drop."
        )
    if sizing["score"] < 100:
        next_actions.append(
            "Enlarge flagged branch segments so they are not smaller than the fixture outlet."
        )
    if code["missing_vent_stack_ids"]:
        next_actions.append(
            "Extend vent stubs above the roof for every stack."
        )

    return {
        "build_status": status,
        "quality_score": overall,
        "dimensions": {
            "connectivity": conn,
            "slope": slope,
            "sizing": sizing,
            "code_compliance": code,
        },
        "metrics": {
            "fixture_count": len(plan.fixtures),
            "stack_count": len(plan.stacks),
            "pipe_segment_count": len(plan.pipes),
            "max_branch_length_mm": round(_max_branch_length(plan), 1),
        },
        "next_actions": next_actions,
    }
