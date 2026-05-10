"""
Typology knowledge pack loader.

This module performs deterministic lookups against JSON knowledge files under
``forge_core/knowledge/typologies/``. It intentionally avoids vector retrieval,
since all queries are keyed by a fixed enumeration of `building_type` values.

Public API:
    - `load_typology(building_type)` returns the typology record.
    - `build_typology_prompt_hint(building_type)` returns a prompt-ready text
      block to be appended to the Architect/Constructor system prompts.
    - `resolve_default(building_type, key, user_value)` returns the user value
      when non-empty, otherwise the typology's configured fallback.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_TYPOLOGY_DIR = os.path.join(_HERE, "typologies")
_DEFAULT_KEY = "default"

# Aliases map user-provided building types (from both slot extraction layers)
# onto the JSON files we ship. Keeping the map explicit keeps the system
# diagnosable and avoids fuzzy matches that drift between releases.
_TYPOLOGY_ALIASES: Dict[str, str] = {
    "office": "office",
    "commercial_office": "office",
    "workplace": "office",
    "residential": "residential",
    "housing": "residential",
    "apartment": "residential",
    "dormitory": "dormitory",
    "dorm": "dormitory",
    "student_dormitory": "dormitory",
    "school": "school",
    "campus": "school",
    "classroom": "school",
    "teaching_building": "school",
    "hospital": "hospital",
    "clinic": "hospital",
    "healthcare": "hospital",
    "hotel": "hotel",
    "resort": "hotel",
    "guesthouse": "hotel",
    "mall": "mall",
    "shopping_mall": "mall",
    "commercial": "mall",
    "retail": "mall",
    "industrial": "industrial",
    "factory": "industrial",
    "warehouse": "industrial",
    "workshop": "industrial",
    "villa": "villa",
    "townhouse": "villa",
    "detached_house": "villa",
    "default": _DEFAULT_KEY,
    "generic": _DEFAULT_KEY,
    "image-guided building": _DEFAULT_KEY,
    "unknown": _DEFAULT_KEY,
}


def _normalize_building_type(building_type: Optional[str]) -> str:
    if not building_type:
        return _DEFAULT_KEY
    key = str(building_type).strip().lower()
    return _TYPOLOGY_ALIASES.get(key, _DEFAULT_KEY)


@lru_cache(maxsize=32)
def _read_typology_file(key: str) -> Dict[str, Any]:
    path = os.path.join(_TYPOLOGY_DIR, f"{key}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def load_typology(building_type: Optional[str]) -> Dict[str, Any]:
    """Returns the typology record for a building type.

    Falls back to the ``default`` typology when the building type is unknown
    or missing. Always returns a dict so callers don't have to null-check.
    """
    primary_key = _normalize_building_type(building_type)
    record = _read_typology_file(primary_key)
    if not record:
        record = _read_typology_file(_DEFAULT_KEY)
    return record or {}


def get_available_typologies() -> List[str]:
    """Lists the typology keys that have a JSON file on disk."""
    if not os.path.isdir(_TYPOLOGY_DIR):
        return []
    result: List[str] = []
    for name in sorted(os.listdir(_TYPOLOGY_DIR)):
        if name.endswith(".json"):
            result.append(name[:-5])
    return result


def resolve_default(
    building_type: Optional[str],
    key: str,
    user_value: Any,
) -> Any:
    """Returns ``user_value`` when non-empty, otherwise the typology fallback.

    Recognised keys include `floor_height_m`, `storey_count`,
    `per_floor_area_m2`, `floor_depth_m`, `structural_grid_m`.
    """
    if user_value not in (None, "", 0, "0"):
        return user_value
    typology = load_typology(building_type)
    fallbacks = typology.get("default_fallbacks") or {}
    return fallbacks.get(key)


def _format_parameter(name: str, spec: Any) -> str:
    if isinstance(spec, dict):
        parts: List[str] = []
        if "typical" in spec:
            parts.append(f"typical={spec['typical']}")
        if "range" in spec and isinstance(spec["range"], list) and len(spec["range"]) == 2:
            parts.append(f"range={spec['range'][0]}-{spec['range'][1]}")
        if "options" in spec and isinstance(spec["options"], list):
            parts.append(f"options={','.join(str(v) for v in spec['options'])}")
        for extra_key in ("single_load", "double_load", "fire_code_min"):
            if extra_key in spec:
                parts.append(f"{extra_key}={spec[extra_key]}")
        note = spec.get("note")
        summary = ", ".join(parts) if parts else json.dumps(spec, ensure_ascii=False)
        if note:
            return f"- {name}: {summary} ({note})"
        return f"- {name}: {summary}"
    return f"- {name}: {spec}"


def _format_program_zones(zones: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        name = zone.get("name") or zone.get("label_en") or "zone"
        ratio = zone.get("ratio")
        area = zone.get("typical_area_m2") or zone.get("min_area_m2")
        adjacency = zone.get("adjacency") or []
        pieces: List[str] = [f"ratio={ratio}" if ratio is not None else ""]
        if area:
            pieces.append(f"typical_area={area} m2")
        if adjacency:
            pieces.append(f"adjacent_to={','.join(adjacency)}")
        descriptor = ", ".join(piece for piece in pieces if piece)
        lines.append(f"- {name}: {descriptor}")
    return lines


def build_typology_prompt_hint(building_type: Optional[str]) -> str:
    """Renders the typology record as a prompt-ready block.

    The output is appended verbatim to both Architect and Constructor prompts.
    The block is stable and self-describing so the LLM can extract values
    deterministically.
    """
    typology = load_typology(building_type)
    if not typology:
        return ""

    label = typology.get("label_zh") or typology.get("label_en") or typology.get("building_type", "")
    header = f"[TYPOLOGY KNOWLEDGE: {typology.get('building_type', 'default')} / {label}]"

    parameter_lines: List[str] = []
    design_parameters = typology.get("design_parameters") or {}
    for name, spec in design_parameters.items():
        parameter_lines.append(_format_parameter(name, spec))

    zone_lines = _format_program_zones(typology.get("program_zones") or [])

    fallback_lines: List[str] = []
    for key, value in (typology.get("default_fallbacks") or {}).items():
        fallback_lines.append(f"- {key}: {value}")

    mass_hint = typology.get("mass_composition_hint") or ""

    example = typology.get("few_shot_example") or {}
    example_lines: List[str] = []
    if example.get("user_input"):
        example_lines.append(f"User: {example['user_input']}")
    if example.get("architect_guidance"):
        example_lines.append(f"Architect guidance: {example['architect_guidance']}")

    blocks: List[str] = [
        header,
        "Design parameters:",
        *parameter_lines,
        "Program zones (approximate ratios):",
        *zone_lines,
        "Default fallbacks (use when the user did not specify a value):",
        *fallback_lines,
    ]
    if mass_hint:
        blocks.append(f"Mass composition hint: {mass_hint}")
    if example_lines:
        blocks.append("Worked example:")
        blocks.extend(example_lines)
    blocks.append(
        "Usage rules: "
        "(1) Always prefer explicit user values over defaults. "
        "(2) When the user omits a parameter, use the typical value above and mark it [inferred]. "
        "(3) Honour the program zone ratios unless the brief demands otherwise. "
        "(4) Do not invent parameters outside this knowledge block."
    )
    return "\n".join(blocks)
