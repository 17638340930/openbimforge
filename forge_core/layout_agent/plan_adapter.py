"""ForgeVision-Layout MVP adapter.

This is a deterministic floor-plan topology adapter. It does not replace the
future trained Layout model; it gives Nexus a stable schema and file lifecycle
now, so the UI/API/LLM/VM chain can be exercised without touching ForgeVision-
Form or Stage 4 execution.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .layout_adapter import make_session_dirs, stage_input_image, validate_input_image


def run_plan_layout(image_path: str, session_id: str | None = None) -> dict[str, Any]:
    resolved_session_id = session_id or f"layout-plan-{uuid.uuid4().hex[:12]}"
    started_at = datetime.now(timezone.utc).isoformat()
    dirs = make_session_dirs(resolved_session_id)
    log_path = dirs["log_dir"] / f"layout_{resolved_session_id}.log"

    try:
        source_image = validate_input_image(image_path)
        staged_image = stage_input_image(source_image, dirs["input_dir"])
        preview_path = dirs["output_dir"] / f"layout_reference{staged_image.suffix.lower()}"
        shutil.copy2(staged_image, preview_path)

        topology = _build_office_layout_topology()
        topology_path = dirs["output_dir"] / "layout_topology.json"
        topology_path.write_text(json.dumps(topology, ensure_ascii=False, indent=2), encoding="utf-8")

        _append_log(
            log_path,
            "\n".join(
                [
                    "[ForgeVision-Layout] MVP topology adapter executed.",
                    f"input={staged_image}",
                    f"preview={preview_path}",
                    f"topology={topology_path}",
                ]
            ),
        )

        return {
            "ok": True,
            "status": "completed_reference_only",
            "session_id": resolved_session_id,
            "started_at": started_at,
            "input_dir": str(dirs["input_dir"]),
            "output_dir": str(dirs["output_dir"]),
            "preview_paths": [str(preview_path)],
            "layout_topology_path": str(topology_path),
            "layout": topology,
            "log_path": str(log_path),
            "error": None,
        }
    except Exception as exc:
        _append_log(log_path, f"[ForgeVision-Layout] failed: {exc}")
        return {
            "ok": False,
            "status": "failed",
            "session_id": resolved_session_id,
            "started_at": started_at,
            "input_dir": str(dirs["input_dir"]),
            "output_dir": str(dirs["output_dir"]),
            "preview_paths": [],
            "layout_topology_path": None,
            "layout": {},
            "log_path": str(log_path),
            "error": str(exc),
        }


def _build_office_layout_topology() -> dict[str, Any]:
    rooms = [
        _room("core", "core", "中央核心筒", [(16, 8), (24, 8), (24, 16), (16, 16)], 64),
        _room("open-office-west", "office", "开放办公区-西", [(0, 0), (16, 0), (16, 24), (0, 24)], 384),
        _room("open-office-east", "office", "开放办公区-东", [(24, 0), (40, 0), (40, 24), (24, 24)], 384),
        _room("meeting-north", "meeting", "会议室组", [(16, 16), (40, 16), (40, 24), (16, 24)], 192),
        _room("service-south", "service", "后勤配套", [(16, 0), (40, 0), (40, 8), (16, 8)], 192),
    ]
    return {
        "schema": "openbimforge.forgevision-layout.v0",
        "inference_method": "rule_based_mvp",
        "scale": {"unit": "m", "width": 40, "depth": 24},
        "rooms": rooms,
        "adjacency": [
            ["core", "open-office-west"],
            ["core", "open-office-east"],
            ["core", "meeting-north"],
            ["core", "service-south"],
            ["open-office-west", "meeting-north"],
            ["open-office-east", "meeting-north"],
        ],
        "circulation": [{"id": "main-loop", "type": "corridor", "widthM": 1.8, "connects": ["core", "meeting-north", "service-south"]}],
        "cores": [{"id": "core", "stairs": 1, "elevators": 2}],
        "notes": [
            "[REFERENCE_ONLY] ForgeVision-Layout MVP provides a schematic floor-plan topology, not final construction geometry.",
            "Use rooms and adjacency to guide native BIM spaces, walls, doors, corridors, and vertical core placement.",
            "Future trained Layout model can replace this adapter without changing the API contract.",
        ],
    }


def _room(
    room_id: str,
    room_type: str,
    name: str,
    polygon: list[tuple[float, float]],
    area_m2: float,
) -> dict[str, Any]:
    return {
        "id": room_id,
        "type": room_type,
        "name": name,
        "polygon": [[x, y] for x, y in polygon],
        "areaM2": area_m2,
        "confidence": 0.6,
    }


def _append_log(log_path: Path, content: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(content)
        if not content.endswith("\n"):
            handle.write("\n")
