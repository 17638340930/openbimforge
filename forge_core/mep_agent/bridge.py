"""
Bridge layer: translates the Architect pipeline state into a
`BuildingPlan` that the MEP agent can consume.

The Architect-Agent persists its reasoning into two sources:

1. ``forge_runtime/state/<session_id>.json`` — the `previous_state` dict
   updated by `UnifiedOpenAICompatibleAgent.chat(... return_code=True)`.
2. The generated Vectorworks Python code, which is our ground-truth of
   geometry.

When the Architect writes a structured ``building_plan`` key into the state
we use it directly. Otherwise we fall back to a heuristic extraction that
parses `create_story_layer` / `create_functional_area` calls out of the
generated code. The heuristic path is lossy, but enough to exercise the MEP
pipeline end-to-end for common templates.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .schema import BuildingPlan, Point2D, Polygon, Room, Shaft, Storey


_STOREY_PATTERN = re.compile(
    r"create_story_layer\s*\(\s*[\"']([^\"']+)[\"']\s*,\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_FUNCTIONAL_AREA_PATTERN = re.compile(
    r"create_functional_area\s*\((?P<args>[^)]*)\)",
    re.IGNORECASE,
)
_NAME_PATTERN = re.compile(r"[\"']([^\"']+)[\"']")
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _infer_room_type(name: str) -> Optional[str]:
    lower = name.lower()
    # Chinese tokens
    if any(token in name for token in ("卫生间", "洗手间", "厕所", "盥洗")):
        if "男" in name:
            return "restroom_public_male"
        if "女" in name:
            return "restroom_public_female"
        return "bathroom"
    # English tokens
    if any(token in lower for token in ("bathroom", "restroom", "wc", "toilet", "lavatory")):
        if "male" in lower or "men" in lower:
            return "restroom_public_male"
        if "female" in lower or "women" in lower:
            return "restroom_public_female"
        return "bathroom"
    if "茶水" in name or "tea" in lower or "pantry" in lower or "break" in lower:
        return "tea_room"
    if "厨" in name or "kitchen" in lower:
        return "kitchen"
    return None


def _extract_rooms_from_code(code: str) -> List[Tuple[str, Polygon]]:
    rooms: List[Tuple[str, Polygon]] = []
    for match in _FUNCTIONAL_AREA_PATTERN.finditer(code):
        args = match.group("args")
        name_match = _NAME_PATTERN.search(args)
        if not name_match:
            continue
        name = name_match.group(1)
        numbers = [float(v) for v in _NUMBER_PATTERN.findall(args)]
        if len(numbers) < 4:
            continue
        if len(numbers) == 4:
            # Treated as bbox (x1, y1, x2, y2).
            x1, y1, x2, y2 = numbers
            polygon = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        else:
            pairs = list(zip(numbers[0::2], numbers[1::2]))
            if len(pairs) < 3:
                continue
            polygon = [(x, y) for x, y in pairs]
        rooms.append((name, polygon))
    return rooms


def _extract_storeys_from_code(code: str) -> List[Tuple[str, float]]:
    storeys: List[Tuple[str, float]] = []
    for match in _STOREY_PATTERN.finditer(code):
        name = match.group(1)
        elevation = float(match.group(2))
        storeys.append((name, elevation))
    return storeys


def building_plan_from_architect_result(
    architect_result: Dict[str, Any],
    *,
    project_name: Optional[str] = None,
    state_path: Optional[str] = None,
) -> BuildingPlan:
    """Builds a `BuildingPlan` from the Architect pipeline's return value.

    Preference order for the source of truth:

    1. ``architect_result["building_plan"]`` — structured output (rare but
       fully lossless).
    2. A sidecar JSON file at ``state_path`` with a ``building_plan`` key.
    3. Heuristic parsing of ``architect_result["code_result"]``.
    """
    for candidate in (
        architect_result.get("building_plan"),
        _read_state_building_plan(state_path) if state_path else None,
    ):
        if isinstance(candidate, dict) and candidate.get("storeys"):
            from .mep_pipeline import _load_building_plan  # lazy to avoid cycles

            return _load_building_plan(candidate)

    code = architect_result.get("code_result") or ""
    name = project_name or architect_result.get("project_name") or "nexus_bim"

    storey_specs = _extract_storeys_from_code(code)
    rooms = _extract_rooms_from_code(code)
    if not storey_specs:
        storey_specs = [("L1", 0.0)]

    # Map every room into the first storey — the Architect emits rooms
    # without storey identifiers today, so multi-storey reasoning is handled
    # later via storey cloning.
    storeys: List[Storey] = []
    for index, (storey_name, elevation) in enumerate(storey_specs):
        storey = Storey(
            id=storey_name,
            index=index,
            elevation_mm=float(elevation),
            height_mm=3600.0,
            outline=_default_outline(rooms),
        )
        for r_idx, (name_, polygon) in enumerate(rooms):
            room_type = _infer_room_type(name_)
            if not room_type:
                continue
            storey.rooms.append(
                Room(
                    id=f"{storey_name}_{r_idx:02d}",
                    storey_id=storey_name,
                    type=room_type,
                    polygon=polygon,
                    label_zh=name_,
                )
            )
        storeys.append(storey)

    return BuildingPlan(
        project_name=name,
        storeys=storeys,
        ceiling_void_mm=500.0,
    )


def _default_outline(rooms: List[Tuple[str, Polygon]]) -> Polygon:
    if not rooms:
        return [(0.0, 0.0), (30000.0, 0.0), (30000.0, 20000.0), (0.0, 20000.0)]
    xs, ys = [], []
    for _, polygon in rooms:
        for x, y in polygon:
            xs.append(x)
            ys.append(y)
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    # Pad the bounding box so the pipe router has clearance outside rooms.
    pad = 2000.0
    return [
        (minx - pad, miny - pad),
        (maxx + pad, miny - pad),
        (maxx + pad, maxy + pad),
        (minx - pad, maxy + pad),
    ]


def _read_state_building_plan(state_path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not state_path or not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(state, dict):
        plan = state.get("building_plan")
        if isinstance(plan, dict):
            return plan
    return None
