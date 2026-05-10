"""
Nexus Checker Agent.

Runs the three-dimensional quality evaluator on the code produced by the
Constructor-Agent and, if the overall score falls below a configurable
threshold, requests a single regeneration attempt with explicit, structured
feedback.

The checker is intentionally **bounded**:

- It only ever runs once. A failed second attempt is not retried further so
  the pipeline cannot loop indefinitely on a poor model response.
- The rewrite instruction is built deterministically from the scored
  dimensions, so the feedback text is stable and testable.

Module exports:
    - `run_checker_stage(...)` — the stage entrypoint used by
      ``run_nexus_architect_pipeline``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional


DEFAULT_CHECKER_THRESHOLD = 80


def _env_threshold() -> int:
    """Resolves the configured checker threshold with safe bounds."""
    raw = os.environ.get("OPENBIMFORGE_CHECKER_THRESHOLD")
    if not raw:
        return DEFAULT_CHECKER_THRESHOLD
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_CHECKER_THRESHOLD
    return max(0, min(100, value))


def _build_rewrite_instruction(
    *,
    report: Dict[str, Any],
    requirements: Dict[str, Any],
    typology_hint: str,
) -> str:
    """Turns a quality report into a Constructor regeneration prompt."""
    dimensions = report.get("dimensions") or {}
    conformance = dimensions.get("requirement_conformance") or {}
    richness = dimensions.get("bim_richness") or {}
    geometry = dimensions.get("geometry_validity") or {}
    overall = report.get("quality_score", 0)

    findings: List[str] = []
    if conformance.get("score", 100) < 80:
        expected_area = conformance.get("area_expected_m2")
        actual_area = conformance.get("area_inferred_m2")
        if expected_area is not None:
            findings.append(
                f"- Per-floor area deviates from the user brief. Expected ~{expected_area} m2, "
                f"generated footprint ~{actual_area if actual_area is not None else 'unknown'} m2."
            )
        expected_storey = conformance.get("storey_expected")
        actual_storey = conformance.get("storey_inferred")
        if expected_storey and (actual_storey or 0) < expected_storey:
            findings.append(
                f"- Storey count too low. Expected {expected_storey} storeys, "
                f"generated {actual_storey}. Call `create_story_layer(...)` for each storey "
                "and duplicate the slab/wall pattern per storey."
            )
        expected_height = conformance.get("floor_height_expected_m")
        if expected_height is not None and conformance.get("floor_height_inferred_m") is None:
            findings.append(
                f"- Floor height not reflected in the code. Apply {expected_height} m "
                f"(~{int(float(expected_height) * 1000)} mm) to wall heights."
            )

    if geometry.get("score", 100) < 85:
        if geometry.get("slab_missing_despite_walls"):
            findings.append("- Walls exist but no slab was created. Add a slab polygon on every storey.")
        if geometry.get("walls_missing_despite_slab"):
            findings.append("- Slab exists but no perimeter walls were created.")
        suspicious = geometry.get("suspicious_polygon_count")
        if suspicious:
            findings.append(
                f"- {suspicious} polygon(s) have fewer than 4 vertices. Rebuild with ordered perimeter polygons."
            )

    if richness.get("score", 100) < 80:
        if not richness.get("has_core_zone"):
            findings.append(
                "- No core zone found. Create a central vertical core via `create_functional_area('core_zone', ...)` "
                "containing elevators, stairs, and shafts."
            )
        if not richness.get("has_circulation_zone"):
            findings.append(
                "- No corridor/circulation zone found. Add `create_functional_area('corridor', ...)` "
                "connecting the core to program zones."
            )
        if (richness.get("wall_count") or 0) < 4:
            findings.append("- Perimeter walls insufficient. Create at least four perimeter walls per storey.")

    if not findings:
        findings.append(
            "- Overall score below threshold but no single dimension stands out. "
            "Enrich the BIM model with storeys, program zones, and an explicit core."
        )

    brief_parts: List[str] = []
    for key in ("building_type", "storey_count", "target_area_m2", "floor_height_m"):
        value = requirements.get(key)
        if value not in (None, "", 0):
            brief_parts.append(f"{key}={value}")
    brief = ", ".join(brief_parts) if brief_parts else "no explicit slots"

    instruction_blocks: List[str] = [
        "[Nexus-Checker feedback] The previous Constructor output fell below the quality threshold.",
        f"Overall score: {overall}/100. Please regenerate the code in a single reply, fixing these findings:",
        *findings,
        "",
        f"User brief slots: {brief}.",
    ]
    if typology_hint:
        instruction_blocks.append("Reference typology knowledge already provided in the system prompt; honour its default parameters.")
    instruction_blocks.extend(
        [
            "",
            "Regenerate the entire Python script. Do not emit explanations outside the code block.",
            "Ensure every storey is declared with `create_story_layer(...)`, each storey has "
            "a slab and perimeter walls, a core zone, and a corridor zone.",
        ],
    )
    return "\n".join(instruction_blocks)


def run_checker_stage(
    *,
    code: str,
    resources: Dict[str, List[str]],
    degradations: List[Dict[str, str]],
    requirements: Dict[str, Any],
    typology_hint: str,
    agent_coder: Any,
    chat_history: str,
    emit_stage_event: Callable[[Dict[str, Any]], None],
    stage_events: List[Dict[str, Any]],
    threshold: Optional[int] = None,
) -> Dict[str, Any]:
    """Evaluates and (optionally) regenerates the generated code.

    Returns a dict with ``code`` (final code), ``quality`` (the final report),
    ``did_rewrite`` (bool), ``initial_quality`` (the pre-rewrite report).
    """
    from forge_core.build_agent.quality_evaluator import evaluate_bim_quality

    active_threshold = threshold if threshold is not None else _env_threshold()
    initial_report = evaluate_bim_quality(
        code=code,
        resources=resources,
        degradations=degradations,
        requirements=requirements,
    )

    initial_score = int(initial_report.get("quality_score", 0))

    event: Dict[str, Any] = {
        "id": "nexus_checker",
        "label": "Checker-Agent (质量审查)",
        "status": "completed",
        "detail": f"Initial quality score {initial_score}/100 (threshold {active_threshold}).",
    }

    if initial_score >= active_threshold:
        stage_events.append(event)
        emit_stage_event(event)
        return {
            "code": code,
            "quality": initial_report,
            "did_rewrite": False,
            "initial_quality": initial_report,
            "threshold": active_threshold,
        }

    rewrite_prompt = _build_rewrite_instruction(
        report=initial_report,
        requirements=requirements,
        typology_hint=typology_hint,
    )

    event["detail"] = (
        f"Initial score {initial_score}/100 below threshold {active_threshold}; "
        "requesting Constructor regeneration."
    )
    stage_events.append(event)
    emit_stage_event(event)

    try:
        _state, revised_code = agent_coder.chat(
            rewrite_prompt,
            chat_history,
            return_code=True,
        )
    except Exception as error:  # pragma: no cover - defensive
        failure_event = {
            "id": "nexus_checker_rewrite",
            "label": "Checker-Agent (重生成)",
            "status": "failed",
            "detail": f"Regeneration call failed: {error}",
        }
        stage_events.append(failure_event)
        emit_stage_event(failure_event)
        return {
            "code": code,
            "quality": initial_report,
            "did_rewrite": False,
            "initial_quality": initial_report,
            "threshold": active_threshold,
            "rewrite_error": str(error),
        }

    revised_code = revised_code or code
    revised_report = evaluate_bim_quality(
        code=revised_code,
        resources=resources,
        degradations=degradations,
        requirements=requirements,
    )
    revised_score = int(revised_report.get("quality_score", 0))

    accepted = revised_score >= initial_score
    final_code = revised_code if accepted else code
    final_report = revised_report if accepted else initial_report

    rewrite_event = {
        "id": "nexus_checker_rewrite",
        "label": "Checker-Agent (重生成)",
        "status": "completed",
        "detail": (
            f"Regenerated score {revised_score}/100 ("
            f"{'accepted' if accepted else 'rejected, keeping original'}"
            ")."
        ),
    }
    stage_events.append(rewrite_event)
    emit_stage_event(rewrite_event)

    return {
        "code": final_code,
        "quality": final_report,
        "did_rewrite": accepted,
        "initial_quality": initial_report,
        "revised_quality": revised_report,
        "threshold": active_threshold,
    }
