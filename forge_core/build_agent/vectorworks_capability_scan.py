import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

import vs  # type: ignore


DEFAULT_PROBE_STYLES = {
    "wall_styles": [
        "Exterior Concrete Wall",
        "Exterior Wood Wall",
        "Exterior Brick Wall",
        "Interior Concrete Wall",
        "Interior Wood Wall",
        "Interior Brick Wall",
    ],
    "slab_styles": [
        "Concrete Slab",
        "Generic-Floor Assembly-300mm",
        "Generic-Slab-150mm",
    ],
    "roof_styles": [
        "Low Slope Concrete w/ Rigid Insulation",
        "Sloped Wood Struct Insul Flat Clay Tile",
    ],
    "roof_slab_styles": [
        "slabstyleroof",
        "Concrete Slab",
        "Generic-Floor Assembly-300mm",
    ],
}

DEFAULT_PROBE_SYMBOLS = {
    "door_symbols": [
        "Door Style 1",
        "Door Style 2",
        "Door Style 3",
        "Door Style 4",
        "Door",
        "Single Door",
    ],
    "window_symbols": [
        "Window Style 1",
        "Window Style 2",
        "Window Style 3",
        "Window Style 4",
        "Window",
        "Fixed Window",
    ],
}


def _style_exists(style_name: str) -> bool:
    try:
        return bool(vs.Name2Index(style_name))
    except Exception:
        return False


def _symbol_exists(symbol_name: str) -> bool:
    try:
        symbol_h = vs.GetObject(symbol_name)
        if not symbol_h:
            return False
        try:
            return vs.GetTypeN(symbol_h) == 16
        except Exception:
            return False
    except Exception:
        return False


def _version_info() -> Dict[str, Any]:
    try:
        major, minor, maintenance, platform, build_num = vs.GetVersionEx()
        return {
            "major": major,
            "minor": minor,
            "maintenance": maintenance,
            "platform": platform,
            "build": build_num,
        }
    except Exception:
        try:
            major, minor, maintenance, platform = vs.GetVersion()
            return {
                "major": major,
                "minor": minor,
                "maintenance": maintenance,
                "platform": platform,
            }
        except Exception:
            return {}


def _tool_policy(manifest: Dict[str, Any]) -> Dict[str, str]:
    return {
        "create_wall": "native",
        "create_polygon": "native_with_vertex_normalization",
        "create_slab": "native_then_fallback_extrude",
        "create_pitched_roof": "native_then_roof_slab_style_fallback",
        "add_door_to_wall": (
            "native"
            if manifest.get("door_symbols")
            else "disabled_no_symbol_fallback_skip"
        ),
        "add_window_to_wall": (
            "native"
            if manifest.get("window_symbols")
            else "disabled_no_symbol_fallback_skip"
        ),
        "ifc_export": "with_ui_requires_user_confirmation",
    }


def _generation_rules(manifest: Dict[str, Any]) -> List[str]:
    rules = [
        "Only call tools listed as native or fallback-supported in tool_policy.",
        "Do not invent Vectorworks style or symbol names.",
        "Use ordered, non-self-intersecting polygon vertices for slab and roof profiles.",
        "Prefer simple rectangular slab/roof profiles for production stability.",
    ]
    if not manifest.get("door_symbols"):
        rules.append("Do not call add_door_to_wall; no door symbols are available.")
    if not manifest.get("window_symbols"):
        rules.append("Do not call add_window_to_wall; no window symbols are available.")
    for key, tool_name in [
        ("wall_styles", "set_wall_style"),
        ("slab_styles", "set_slab_style"),
        ("roof_styles", "set_pitched_roof_style"),
    ]:
        if not manifest.get(key):
            rules.append(f"Do not call {tool_name}; no matching styles are available.")
    return rules


def scan_capabilities() -> Dict[str, Any]:
    manifest: Dict[str, Any] = {
        "schema_version": "Nexus Synthesis Capability Contract 1.0",
        "scanned_at": datetime.now().isoformat(),
        "environment": {
            "vectorworks_version": _version_info(),
        },
    }
    for category, candidates in DEFAULT_PROBE_STYLES.items():
        manifest[category] = [
            style_name for style_name in candidates if _style_exists(style_name)
        ]
    for category, candidates in DEFAULT_PROBE_SYMBOLS.items():
        manifest[category] = [
            symbol_name for symbol_name in candidates if _symbol_exists(symbol_name)
        ]
    manifest["tool_policy"] = _tool_policy(manifest)
    manifest["generation_rules"] = _generation_rules(manifest)
    return manifest


def write_manifest(output_path: str) -> str:
    manifest = scan_capabilities()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def default_manifest_path(project_root: str) -> str:
    runtime_root = os.environ.get(
        "OPENBIMFORGE_RUNTIME_ROOT",
        str(Path(project_root) / "forge_runtime"),
    )
    return str(
        Path(runtime_root) / "capabilities" / "vectorworks_styles.json"
    )


if __name__ == "__main__":
    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
    path = write_manifest(default_manifest_path(project_root))
    print(path)
