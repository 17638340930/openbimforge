"""
Nexus BIM quality evaluator.

Replaces the old resource-only score with a three-dimensional assessment that
better reflects how well the generated BIM matches the user's brief and
architectural common sense:

1. ``requirement_conformance`` — how closely the generated code meets the
   user-supplied slots (area, storey count, floor height).
2. ``geometry_validity`` — static checks on polygon/wall/slab constructions
   extracted from the generated Python code.
3. ``bim_richness`` — richness of the BIM semantics (number of storeys, walls,
   slabs, spaces, whether a core or circulation zone was produced, whether
   Vectorworks resources are available).

The evaluator is intentionally static: it analyses the *generated Python code*
and the Vectorworks capability manifest, without requiring a running
Vectorworks instance. This keeps it runnable in dry-run mode and in CI.

The returned dict is backwards-compatible with the old
``_build_quality_report`` contract (it still exposes `build_status`,
`quality_score`, `native_bim_score`, `degradation_count`, and
`missing_resources`), so downstream frontend code continues to work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TOOL_CALL_PATTERN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")


def _count_tool_calls(code: str, tool_names: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {name: 0 for name in tool_names}
    if not code:
        return counts
    for match in _TOOL_CALL_PATTERN.finditer(code):
        name = match.group(1)
        if name in counts:
            counts[name] += 1
    return counts


def _extract_numbers(argument_text: str) -> List[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", argument_text)]


def _find_call_arguments(code: str, tool_name: str) -> List[str]:
    """Returns the raw argument strings for every call of ``tool_name``."""
    pattern = re.compile(rf"\b{re.escape(tool_name)}\s*\(")
    results: List[str] = []
    for match in pattern.finditer(code):
        start = match.end()
        depth = 1
        index = start
        while index < len(code) and depth > 0:
            ch = code[index]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    results.append(code[start:index])
                    break
            index += 1
    return results


@dataclass
class _AggregatedMetrics:
    storey_count: int
    wall_count: int
    slab_count: int
    space_count: int
    polygon_count: int
    roof_count: int
    door_count: int
    window_count: int
    inferred_area_m2: Optional[float]
    inferred_floor_height_m: Optional[float]


def _aggregate_metrics(code: str) -> _AggregatedMetrics:
    counts = _count_tool_calls(
        code,
        (
            "create_wall",
            "create_slab",
            "create_functional_area",
            "create_polygon",
            "create_pitched_roof",
            "create_story_layer",
            "set_active_story_layer",
            "add_door_to_wall",
            "add_window_to_wall",
        ),
    )

    inferred_area: Optional[float] = None
    slab_arguments = _find_call_arguments(code, "create_slab")
    for slab_args in slab_arguments:
        numbers = _extract_numbers(slab_args)
        if len(numbers) >= 8 and len(numbers) % 2 == 0:
            xs = numbers[0::2]
            ys = numbers[1::2]
            width = max(xs) - min(xs)
            depth = max(ys) - min(ys)
            if width > 0 and depth > 0:
                inferred_area = max(inferred_area or 0.0, width * depth / 1_000_000.0)
            break

    inferred_height: Optional[float] = None
    for call_name in ("set_wall_elevation", "set_wall_height"):
        for args_text in _find_call_arguments(code, call_name):
            numbers = _extract_numbers(args_text)
            if numbers:
                tallest = max(abs(value) for value in numbers)
                if tallest > 100:  # assume millimetres
                    inferred_height = max(inferred_height or 0.0, tallest / 1000.0)
                else:
                    inferred_height = max(inferred_height or 0.0, tallest)

    return _AggregatedMetrics(
        storey_count=counts["create_story_layer"] or counts["set_active_story_layer"],
        wall_count=counts["create_wall"],
        slab_count=counts["create_slab"],
        space_count=counts["create_functional_area"],
        polygon_count=counts["create_polygon"],
        roof_count=counts["create_pitched_roof"],
        door_count=counts["add_door_to_wall"],
        window_count=counts["add_window_to_wall"],
        inferred_area_m2=inferred_area,
        inferred_floor_height_m=inferred_height,
    )


def _score_requirement_conformance(
    metrics: _AggregatedMetrics,
    requirements: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    """0-100 score reflecting how closely the model matches user slots."""
    details: Dict[str, Any] = {}
    penalties: List[int] = []

    target_area = _coerce_float(requirements.get("target_area_m2"))
    storey_count = _coerce_int(requirements.get("storey_count"))
    floor_height = _coerce_float(requirements.get("floor_height_m"))

    if target_area and metrics.inferred_area_m2:
        # Per-floor area. If total area requested, divide by storey count.
        expected = target_area
        if storey_count and storey_count > 1:
            expected = target_area / storey_count
        deviation = abs(metrics.inferred_area_m2 - expected) / expected
        details["area_expected_m2"] = round(expected, 1)
        details["area_inferred_m2"] = round(metrics.inferred_area_m2, 1)
        details["area_deviation_pct"] = round(deviation * 100, 1)
        if deviation > 0.5:
            penalties.append(40)
        elif deviation > 0.25:
            penalties.append(20)
        elif deviation > 0.1:
            penalties.append(8)
    elif target_area:
        details["area_expected_m2"] = target_area
        details["area_inferred_m2"] = None
        penalties.append(10)

    if storey_count:
        inferred = metrics.storey_count or 0
        details["storey_expected"] = storey_count
        details["storey_inferred"] = inferred
        if inferred == 0:
            penalties.append(25)
        elif inferred < storey_count:
            penalties.append(min(20, (storey_count - inferred) * 5))
        elif inferred > storey_count * 2:
            penalties.append(10)

    if floor_height and metrics.inferred_floor_height_m:
        deviation = abs(metrics.inferred_floor_height_m - floor_height) / floor_height
        details["floor_height_expected_m"] = floor_height
        details["floor_height_inferred_m"] = round(metrics.inferred_floor_height_m, 2)
        if deviation > 0.3:
            penalties.append(10)
        elif deviation > 0.15:
            penalties.append(5)

    score = max(0, 100 - sum(penalties))
    details["score"] = score
    return score, details


def _score_geometry_validity(
    metrics: _AggregatedMetrics,
    code: str,
) -> Tuple[int, Dict[str, Any]]:
    details: Dict[str, Any] = {
        "wall_count": metrics.wall_count,
        "slab_count": metrics.slab_count,
        "polygon_count": metrics.polygon_count,
    }
    penalties = 0

    if metrics.slab_count == 0 and metrics.wall_count > 0:
        penalties += 25
        details["slab_missing_despite_walls"] = True

    if metrics.wall_count == 0 and metrics.slab_count > 0:
        penalties += 20
        details["walls_missing_despite_slab"] = True

    # A slab/polygon with fewer than 4 vertices is suspicious for buildings.
    suspicious_polys = 0
    for args_text in _find_call_arguments(code, "create_slab") + _find_call_arguments(code, "create_polygon"):
        numbers = _extract_numbers(args_text)
        if numbers and len(numbers) < 8:
            suspicious_polys += 1
    if suspicious_polys:
        penalties += min(15, suspicious_polys * 5)
        details["suspicious_polygon_count"] = suspicious_polys

    score = max(0, 100 - penalties)
    details["score"] = score
    return score, details


def _score_bim_richness(
    metrics: _AggregatedMetrics,
    code: str,
    resources: Dict[str, List[str]],
    degradations: List[Dict[str, str]],
) -> Tuple[int, Dict[str, Any], List[str]]:
    missing_resources: List[str] = []
    penalties = 0
    details: Dict[str, Any] = {
        "storey_count": metrics.storey_count,
        "wall_count": metrics.wall_count,
        "slab_count": metrics.slab_count,
        "space_count": metrics.space_count,
        "roof_count": metrics.roof_count,
        "door_count": metrics.door_count,
        "window_count": metrics.window_count,
    }

    lower_code = code.lower()
    has_core = any(token in lower_code for token in ("core", "核心筒", "core_zone"))
    has_circulation = any(token in lower_code for token in ("corridor", "circulation", "走廊"))
    details["has_core_zone"] = has_core
    details["has_circulation_zone"] = has_circulation

    if metrics.storey_count == 0:
        penalties += 18
    if metrics.space_count == 0:
        penalties += 10
    if not has_core:
        penalties += 10
    if not has_circulation:
        penalties += 8
    if metrics.wall_count < 4:
        penalties += 12

    if not resources.get("door_symbols"):
        penalties += 4
        missing_resources.append("door_symbols")
    if not resources.get("window_symbols"):
        penalties += 4
        missing_resources.append("window_symbols")
    if not resources.get("slab_styles"):
        penalties += 2
        missing_resources.append("slab_styles")
    if not resources.get("roof_styles"):
        penalties += 2
        missing_resources.append("roof_styles")

    penalties += min(len(degradations) * 2, 12)

    score = max(0, 100 - penalties)
    details["score"] = score
    details["missing_resources"] = missing_resources
    return score, details, missing_resources


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def evaluate_bim_quality(
    *,
    code: str,
    resources: Dict[str, List[str]],
    degradations: List[Dict[str, str]],
    requirements: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Returns a three-dimensional quality report plus a weighted overall score.

    The returned dict includes legacy keys (`build_status`, `quality_score`,
    `native_bim_score`, `degradation_count`, `missing_resources`) so existing
    consumers continue to work without change.
    """
    requirements = requirements or {}
    metrics = _aggregate_metrics(code or "")

    conformance_score, conformance_detail = _score_requirement_conformance(metrics, requirements)
    geometry_score, geometry_detail = _score_geometry_validity(metrics, code or "")
    richness_score, richness_detail, missing_resources = _score_bim_richness(
        metrics,
        code or "",
        resources,
        degradations,
    )

    overall = round(
        conformance_score * 0.4 + geometry_score * 0.3 + richness_score * 0.3,
    )
    overall = max(0, min(100, int(overall)))
    if overall >= 85:
        status = "success"
    elif overall >= 60:
        status = "partial_success"
    else:
        status = "needs_revision"

    next_actions: List[str] = []
    if missing_resources:
        next_actions.append(
            "Load a Vectorworks template with door/window/slab/roof styles, then re-run the capability scan.",
        )
    if conformance_score < 80:
        next_actions.append(
            "Regenerate with tighter adherence to user-supplied slots (area/storey/floor height).",
        )
    if geometry_score < 80:
        next_actions.append(
            "Ask the Constructor-Agent to recompute perimeter polygons with at least four vertices and aligned slab/wall boundaries.",
        )
    if richness_score < 70:
        next_actions.append(
            "Request the Architect-Agent to add a vertical core, circulation corridor, and multi-storey layering.",
        )

    report: Dict[str, Any] = {
        "build_status": status,
        "quality_score": overall,
        "native_bim_score": max(0, overall - (10 if degradations else 0)),
        "fallback_score": 100 if degradations else 0,
        "degradation_count": len(degradations),
        "missing_resources": missing_resources,
        "metrics": {
            "storey_count": metrics.storey_count,
            "wall_count": metrics.wall_count,
            "slab_count": metrics.slab_count,
            "space_count": metrics.space_count,
            "polygon_count": metrics.polygon_count,
            "roof_count": metrics.roof_count,
            "door_count": metrics.door_count,
            "window_count": metrics.window_count,
            "inferred_area_m2": metrics.inferred_area_m2,
            "inferred_floor_height_m": metrics.inferred_floor_height_m,
        },
        "dimensions": {
            "requirement_conformance": conformance_detail,
            "geometry_validity": geometry_detail,
            "bim_richness": richness_detail,
        },
        "next_actions": next_actions,
    }
    return report
