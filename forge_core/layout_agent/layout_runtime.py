"""Runtime orchestration for openBIMForge Layout Agent."""

from __future__ import annotations

import subprocess
import traceback
import uuid
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .layout_adapter import (
    build_inference_command,
    index_outputs,
    load_runtime_config,
    make_session_dirs,
    stage_input_image,
    validate_input_image,
)


def run_layout(image_path: str, session_id: str | None = None) -> dict[str, Any]:
    resolved_session_id = session_id or f"layout-{uuid.uuid4().hex[:12]}"
    started_at = datetime.now(timezone.utc).isoformat()
    dirs = make_session_dirs(resolved_session_id)
    log_path = dirs["log_dir"] / f"layout_{resolved_session_id}.log"

    try:
        config = load_runtime_config()
        source_image = validate_input_image(image_path)
        staged_image = stage_input_image(source_image, dirs["input_dir"])
        command = build_inference_command(config, dirs["input_dir"])

        completed = _run_command(
            command=command,
            cwd=config.engine_root,
            timeout_ms=config.timeout_ms,
            log_path=log_path,
        )
        if completed.returncode != 0:
            return _result(
                ok=False,
                status="failed",
                session_id=resolved_session_id,
                started_at=started_at,
                input_dir=dirs["input_dir"],
                output_dir=dirs["output_dir"],
                log_path=log_path,
                error="Layout Engine execution failed. Check the log file for details.",
            )

        outputs = index_outputs(dirs["input_dir"], dirs["output_dir"])
        if not outputs["stl_paths"] and not outputs["preview_paths"]:
            fallback_preview = dirs["output_dir"] / f"reference{staged_image.suffix.lower()}"
            shutil.copy2(staged_image, fallback_preview)
            return _result(
                ok=True,
                status="completed_reference_only",
                session_id=resolved_session_id,
                started_at=started_at,
                input_dir=dirs["input_dir"],
                output_dir=dirs["output_dir"],
                log_path=log_path,
                preview_paths=[str(fallback_preview)],
            )

        return _result(
            ok=True,
            status="completed",
            session_id=resolved_session_id,
            started_at=started_at,
            input_dir=dirs["input_dir"],
            output_dir=dirs["output_dir"],
            log_path=log_path,
            preview_paths=outputs["preview_paths"],
            stl_paths=outputs["stl_paths"],
        )
    except subprocess.TimeoutExpired:
        return _result(
            ok=False,
            status="timeout",
            session_id=resolved_session_id,
            started_at=started_at,
            input_dir=dirs["input_dir"],
            output_dir=dirs["output_dir"],
            log_path=log_path,
            error="Layout Engine timed out. Try a smaller image or increase OPENBIMFORGE_LAYOUT_TIMEOUT_MS.",
        )
    except Exception as exc:
        _append_log(log_path, traceback.format_exc())
        return _result(
            ok=False,
            status="failed",
            session_id=resolved_session_id,
            started_at=started_at,
            input_dir=dirs["input_dir"],
            output_dir=dirs["output_dir"],
            log_path=log_path,
            error=str(exc),
        )


def _run_command(
    *,
    command: list[str],
    cwd: Path,
    timeout_ms: int,
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    _append_log(log_path, f"$ {' '.join(command)}\n")
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    python_path = Path(command[0])
    if python_path.is_file():
        env_root = python_path.parent.parent
        path_entries = [
            str(python_path.parent),
            str(env_root / "Library" / "bin"),
            str(env_root / "Scripts"),
        ]
        env["PATH"] = os.pathsep.join(path_entries + [env.get("PATH", "")])
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_ms / 1000,
        check=False,
    )
    _append_log(log_path, "\n[stdout]\n" + (completed.stdout or ""))
    _append_log(log_path, "\n[stderr]\n" + (completed.stderr or ""))
    return completed


def _append_log(log_path: Path, content: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(content)
        if not content.endswith("\n"):
            handle.write("\n")


def _result(
    *,
    ok: bool,
    status: str,
    session_id: str,
    started_at: str,
    input_dir: Path,
    output_dir: Path,
    log_path: Path,
    preview_paths: list[str] | None = None,
    stl_paths: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "status": status,
        "session_id": session_id,
        "started_at": started_at,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "preview_paths": preview_paths or [],
        "stl_paths": stl_paths or [],
        "log_path": str(log_path),
        "error": error,
    }
