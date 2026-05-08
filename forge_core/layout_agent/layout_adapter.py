"""Filesystem and command helpers for the ForgeVision-Form backend adapter.

This module keeps compatibility with the existing external Layout/GenCAD-style
engine while exposing its outputs as ForgeVision-Form massing references.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_TIMEOUT_MS = 900_000


@dataclass(frozen=True)
class LayoutRuntimeConfig:
    engine_root: Path
    entrypoint: Path
    python_command: str
    timeout_ms: int


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_runtime_root() -> Path:
    return Path(os.environ.get("OPENBIMFORGE_RUNTIME_ROOT", get_project_root() / "forge_runtime")).resolve()


def load_runtime_config() -> LayoutRuntimeConfig:
    engine_root_raw = os.environ.get("OPENBIMFORGE_LAYOUT_ENGINE_ROOT", "").strip()
    entrypoint_raw = os.environ.get("OPENBIMFORGE_LAYOUT_ENTRYPOINT", "").strip()
    python_command = os.environ.get("OPENBIMFORGE_LAYOUT_PYTHON", "").strip()
    timeout_raw = os.environ.get("OPENBIMFORGE_LAYOUT_TIMEOUT_MS", str(DEFAULT_TIMEOUT_MS)).strip()

    missing = [
        name
        for name, value in (
            ("OPENBIMFORGE_LAYOUT_ENGINE_ROOT", engine_root_raw),
            ("OPENBIMFORGE_LAYOUT_ENTRYPOINT", entrypoint_raw),
            ("OPENBIMFORGE_LAYOUT_PYTHON", python_command),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            "Layout Engine is not configured. Missing environment variable(s): "
            + ", ".join(missing)
        )

    try:
        timeout_ms = int(timeout_raw)
    except ValueError as exc:
        raise ValueError("OPENBIMFORGE_LAYOUT_TIMEOUT_MS must be an integer.") from exc

    engine_root = Path(engine_root_raw).resolve()
    entrypoint = Path(entrypoint_raw)
    if not entrypoint.is_absolute():
        entrypoint = (engine_root / entrypoint).resolve()

    validate_runtime_paths(engine_root, entrypoint)
    return LayoutRuntimeConfig(
        engine_root=engine_root,
        entrypoint=entrypoint,
        python_command=python_command,
        timeout_ms=timeout_ms,
    )


def validate_runtime_paths(engine_root: Path, entrypoint: Path) -> None:
    if not engine_root.is_dir():
        raise FileNotFoundError(f"Layout Engine root does not exist: {engine_root}")
    if not entrypoint.is_file():
        raise FileNotFoundError(f"Layout Engine entrypoint does not exist: {entrypoint}")


def validate_input_image(image_path: str | Path) -> Path:
    path = Path(image_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Input image does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(
            "Unsupported image format. Please upload PNG, JPG, JPEG, or WebP."
        )
    return path


def make_session_dirs(session_id: str) -> dict[str, Path]:
    runtime_root = get_runtime_root()
    paths = {
        "input_dir": runtime_root / "layout_inputs" / session_id,
        "output_dir": runtime_root / "layout_outputs" / session_id,
        "log_dir": runtime_root / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def stage_input_image(image_path: Path, input_dir: Path) -> Path:
    staged_path = input_dir / f"input{image_path.suffix.lower()}"
    shutil.copy2(image_path, staged_path)
    return staged_path


def build_inference_command(config: LayoutRuntimeConfig, input_dir: Path) -> list[str]:
    return [
        config.python_command,
        str(config.entrypoint),
        "-image_path",
        str(input_dir),
        "-export_stl",
        "-export_img",
    ]


def index_outputs(input_dir: Path, output_dir: Path) -> dict[str, list[str]]:
    stl_paths = _copy_matching(input_dir / "stls", output_dir, "*.stl")
    preview_paths = _copy_matching(input_dir / "generated_images", output_dir, "*.png")
    cad_vector_paths = _copy_matching(input_dir / "cad_vectors", output_dir, "*.json")
    return {
        "stl_paths": [str(path) for path in stl_paths],
        "preview_paths": [str(path) for path in preview_paths],
        "cad_vector_paths": [str(path) for path in cad_vector_paths],
    }


def _copy_matching(source_dir: Path, output_dir: Path, pattern: str) -> list[Path]:
    if not source_dir.is_dir():
        return []
    copied: list[Path] = []
    for source in sorted(source_dir.glob(pattern)):
        destination = output_dir / source.name
        shutil.copy2(source, destination)
        copied.append(destination)
    return copied
