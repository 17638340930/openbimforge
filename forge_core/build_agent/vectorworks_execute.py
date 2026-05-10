import argparse
import json
import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


STYLE_MANIFEST_ENV = "OPENBIMFORGE_STYLE_MANIFEST_PATH"


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _save_json(path: str, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _merge_manifest(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _load_manifest_from_path(path_value: str) -> Dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _effective_style_manifest(
    payload: Dict[str, Any],
    project_root: str,
) -> Dict[str, Any]:
    execution = payload.get("execution_config") or {}
    configured_path = str(
        execution.get("styleManifestPath")
        or os.environ.get(STYLE_MANIFEST_ENV, "")
        or ""
    )
    runtime_root = Path(
        os.environ.get(
            "OPENBIMFORGE_RUNTIME_ROOT",
            str(Path(project_root) / "forge_runtime"),
        )
    )
    default_path = str(runtime_root / "capabilities" / "vectorworks_styles.json")
    manifest = _load_manifest_from_path(default_path)
    manifest = _merge_manifest(manifest, _load_manifest_from_path(configured_path))
    manifest = _merge_manifest(manifest, payload.get("style_manifest", {}) or {})
    return manifest


def _resolve_output_dir(payload: dict) -> Path:
    execution = payload.get("execution_config") or {}
    output_root = execution.get("outputRoot") or os.path.join(
        os.environ.get(
            "OPENBIMFORGE_RUNTIME_ROOT",
            os.path.join(os.environ.get("PROJECT_ROOT", os.getcwd()), "forge_runtime"),
        ),
        "artifacts",
    )
    return Path(output_root)


def _strip_code_fences(code: str) -> str:
    text = (code or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _tool_policy(payload: Dict[str, Any]) -> Dict[str, str]:
    manifest = payload.get("style_manifest", {}) or {}
    policy = manifest.get("tool_policy", {})
    return policy if isinstance(policy, dict) else {}


def _resources(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    manifest = payload.get("style_manifest", {}) or {}
    return {
        "door_symbols": _normalize_style_list(manifest.get("door_symbols")),
        "window_symbols": _normalize_style_list(manifest.get("window_symbols")),
        "wall_styles": _normalize_style_list(manifest.get("wall_styles")),
        "slab_styles": _normalize_style_list(manifest.get("slab_styles")),
        "roof_styles": _normalize_style_list(manifest.get("roof_styles")),
        "roof_slab_styles": _normalize_style_list(manifest.get("roof_slab_styles")),
    }


def _replace_tool_call_line(line: str, tool_name: str, replacement: str) -> Tuple[str, bool]:
    if f"{tool_name}(" not in line:
        return line, False
    indent = line[: len(line) - len(line.lstrip())]
    if "=" in line and line.index("=") < line.index(f"{tool_name}("):
        variable = line.split("=", 1)[0].strip()
        return f"{indent}{variable} = {replacement}", True
    return f"{indent}{replacement}", True


def _static_validate_and_rewrite_code(
    payload: Dict[str, Any],
    code: str,
) -> Tuple[str, Dict[str, Any]]:
    policy = _tool_policy(payload)
    resources = _resources(payload)
    lines = code.splitlines()
    rewritten: List[str] = []
    degradations: List[Dict[str, str]] = []

    door_disabled = (
        policy.get("add_door_to_wall", "").startswith("disabled")
        or not resources["door_symbols"]
    )
    window_disabled = (
        policy.get("add_window_to_wall", "").startswith("disabled")
        or not resources["window_symbols"]
    )

    for line in lines:
        next_line = line
        if door_disabled:
            next_line, changed = _replace_tool_call_line(
                next_line,
                "add_door_to_wall",
                '""  # openBIMForge: door skipped, no door symbol in Tool Contract',
            )
            if changed:
                degradations.append(
                    {
                        "code": "door_symbol_missing",
                        "severity": "warning",
                        "message": "Removed add_door_to_wall call because the current Vectorworks file has no available door symbols.",
                    }
                )
        if window_disabled:
            next_line, changed = _replace_tool_call_line(
                next_line,
                "add_window_to_wall",
                '""  # openBIMForge: window skipped, no window symbol in Tool Contract',
            )
            if changed:
                degradations.append(
                    {
                        "code": "window_symbol_missing",
                        "severity": "warning",
                        "message": "Removed add_window_to_wall call because the current Vectorworks file has no available window symbols.",
                    }
                )
        rewritten.append(next_line)

    rewritten_code = "\n".join(rewritten)
    unresolved_disabled_calls: List[str] = []
    if door_disabled and "add_door_to_wall(" in rewritten_code:
        unresolved_disabled_calls.append("add_door_to_wall")
    if window_disabled and "add_window_to_wall(" in rewritten_code:
        unresolved_disabled_calls.append("add_window_to_wall")
    for tool_name in unresolved_disabled_calls:
        degradations.append(
            {
                "code": "disabled_tool_call_unresolved",
                "severity": "error",
                "message": f"Disabled tool call remains after static rewrite: {tool_name}. Send this result to the Diagnostic Agent if execution fails.",
            }
        )

    validation = {
        "tool_policy": policy,
        "resources": resources,
        "degradations": degradations,
        "unresolved_disabled_calls": unresolved_disabled_calls,
        "rewrote_code": rewritten_code != code,
        "quality": _build_quality_report(
            rewritten_code,
            resources,
            degradations,
            payload.get("requirement_slots") or payload.get("semantic_slots") or {},
        ),
    }
    return rewritten_code, validation


def _build_quality_report(
    code: str,
    resources: Dict[str, List[str]],
    degradations: List[Dict[str, str]],
    requirements: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Delegates to the three-dimensional quality evaluator.

    Kept as a free function here so callers inside ``vectorworks_execute`` keep
    working, but the real logic lives in
    ``forge_core.build_agent.quality_evaluator``.
    """
    from forge_core.build_agent.quality_evaluator import evaluate_bim_quality

    return evaluate_bim_quality(
        code=code or "",
        resources=resources,
        degradations=degradations,
        requirements=requirements or {},
    )


def _build_execution_namespace() -> dict:
    import vs  # type: ignore
    from tool_agent import vw_tools_extend as tools  # type: ignore

    namespace = {
        "__builtins__": __builtins__,
        "vs": vs,
        "create_story_layer": tools.CreateStoryLayer(),
        "set_active_story_layer": tools.SetStoryLayerActive(),
        "create_functional_area": tools.CreateSpace(),
        "create_wall": tools.CreateWallTool(),
        "set_wall_thickness": tools.SetWallThickness(),
        "set_wall_elevation": tools.SetWallHeight(),
        "get_wall_elevation": tools.GetWallElevation(),
        "get_wall_thickness": tools.GetWallThickness(),
        "set_wall_style": tools.SetWallStyle(),
        "add_window_to_wall": tools.AddWindowToWall(),
        "add_door_to_wall": tools.AddDoorToWall(),
        "move": tools.Move(),
        "delete_element": tools.DeleteTool(),
        "find_selected_element": tools.FindSelect(),
        "create_polygon": tools.CreatePolygon(),
        "get_polygon_vertex": tools.GetPolygonVertex(),
        "get_vert_num": tools.GetVertNum(),
        "create_slab": tools.CreateSlab(),
        "set_slab_height": tools.SetSlabHeight(),
        "get_slab_height": tools.GetSlabHeight(),
        "set_slab_style": tools.SetSlabStyle(),
        "duplicate_obj": tools.DuplicateObj(),
        "rotate_obj": tools.RotateObj(),
        "create_pitched_roof": tools.CreateRoof(),
        "set_roof_attributes": tools.SetRoofAttributes(),
        "set_pitched_roof_style": tools.SetRoofStyle(),
    }
    return namespace


def _ensure_project_import_paths(project_root: str) -> None:
    import sys

    root = Path(project_root)
    for candidate in (
        root,
        root / "forge_core",
        root / "forge_core" / "design_agent",
        root / "forge_core" / "build_agent",
    ):
        candidate_text = str(candidate)
        if candidate_text not in sys.path:
            sys.path.insert(0, candidate_text)


def _execute_generated_code(payload: Dict[str, Any], code: str) -> dict:
    cleaned_code = _strip_code_fences(code)
    if not cleaned_code:
        raise RuntimeError("Missing generated Vectorworks code in handoff payload")
    validated_code, validation = _static_validate_and_rewrite_code(
        payload,
        cleaned_code,
    )

    namespace = _build_execution_namespace()
    exec(validated_code, namespace, namespace)
    return {
        "code_lines": len(validated_code.splitlines()),
        "validation": validation,
        "executed_code": validated_code,
    }


def _export_vectorworks_artifacts(output_dir: Path, stem: str) -> dict:
    import vs  # type: ignore

    output_dir.mkdir(parents=True, exist_ok=True)
    vwx_path = output_dir / f"{stem}.vwx"
    ifc_path = output_dir / f"{stem}.ifc"
    search_dirs = [output_dir, Path.cwd()]
    before_ifc_files = {
        str(item.resolve())
        for folder in search_dirs
        if folder.exists()
        for item in folder.glob("*.ifc")
    }

    vs.SaveActiveDocument(str(vwx_path))
    vs.IFC_ExportWithUI(False)

    after_ifc_files = [
        item
        for folder in search_dirs
        if folder.exists()
        for item in folder.glob("*.ifc")
    ]
    new_ifc_files = [
        item for item in after_ifc_files if str(item.resolve()) not in before_ifc_files
    ]
    if not ifc_path.exists() and new_ifc_files:
        newest_ifc = max(new_ifc_files, key=lambda item: item.stat().st_mtime)
        ifc_path = newest_ifc

    recovered_ifc_path = ""
    if not ifc_path.exists():
        recovered_ifc = _find_named_ifc_export(stem, output_dir)
        if recovered_ifc:
            recovered_ifc_path = str(recovered_ifc)
            try:
                shutil.copy2(str(recovered_ifc), str(ifc_path))
            except Exception:
                ifc_path = recovered_ifc

    ifc_exists = ifc_path.exists()
    ifc_status = "ready" if ifc_exists else "not_found_after_export"
    ifc_message = (
        "IFC artifact was found."
        if ifc_exists
        else (
            "Vectorworks code executed and VWX was saved, but no IFC file was found. "
            "When the Export IFC Project dialog appears, confirm the export and set "
            f"the output path to {output_dir / f'{stem}.ifc'}."
        )
    )

    return {
        "vwx_path": str(vwx_path),
        "ifc_path": str(ifc_path),
        "ifc_source_path": recovered_ifc_path,
        "ifc_ready": ifc_exists,
        "ifc_status": ifc_status,
        "ifc_message": ifc_message,
    }


def _find_named_ifc_export(stem: str, output_dir: Path) -> Optional[Path]:
    home = Path.home()
    candidate_dirs = [
        output_dir,
        Path.cwd(),
        home / "Downloads",
        home / "Desktop",
        home / "Documents",
    ]
    candidate_patterns = [
        f"{stem}.ifc",
        f"{stem}-*.ifc",
        f"{stem}_*.ifc",
    ]

    matches: List[Path] = []
    seen: set[str] = set()
    for folder in candidate_dirs:
        if not folder.exists():
            continue
        for pattern in candidate_patterns:
            for candidate in folder.glob(pattern):
                try:
                    resolved = str(candidate.resolve())
                except OSError:
                    resolved = str(candidate)
                if resolved in seen or not candidate.is_file():
                    continue
                seen.add(resolved)
                matches.append(candidate)

    if not matches:
        return None
    return max(matches, key=lambda item: item.stat().st_mtime)


def _extract_missing_style(error_text: str) -> Optional[str]:
    match = re.search(r"Style name ([^\n]+?) not found", error_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _classify_error(error_text: str) -> Dict[str, str]:
    lower = error_text.lower()
    summary = "Nexus-Constructor synthesis failed."
    category = "code_error"

    if "style name" in lower and "not found" in lower:
        category = "resource_error"
        summary = "Vectorworks style resource is missing."
    elif "self-intersecting boundary" in lower or "slab cannot be created" in lower:
        category = "geometry_error"
        summary = "Generated polygon boundary is invalid for slab creation."
    elif "handle variable is nil" in lower:
        category = "code_error"
        summary = "A Vectorworks handle was nil during execution."
    elif "nameerror" in lower and "is not defined" in lower:
        category = "code_error"
        summary = "Generated code referenced a tool function or variable that is not available."
    elif "modulenotfounderror" in lower or "no module named" in lower:
        category = "environment_error"
        summary = "Vectorworks Python environment is missing a required module."
    elif "permission" in lower or "access is denied" in lower:
        category = "environment_error"
        summary = "Vectorworks could not write an output artifact."
    elif "missing handoff" in lower or "project root" in lower:
        category = "configuration_error"
        summary = "Execution handoff is incomplete."

    return {
        "category": category,
        "summary": summary,
    }


def _normalize_style_list(values: Any) -> List[str]:
    return [str(value) for value in (values or []) if str(value).strip()]


def _build_fixer_payload(
    payload: Dict[str, Any],
    previous_code: str,
    error_text: str,
    classification: Dict[str, str],
    retry_index: int,
    max_retries: int,
) -> Dict[str, Any]:
    return {
        "task_id": f"{payload.get('execution_config', {}).get('jobName', 'nexus-synthesis')}-attempt-{retry_index}",
        "user_requirement": payload.get("query", ""),
        "original_plan": payload.get("agent_output", ""),
        "previous_code": previous_code,
        "execution_mode": "vectorworks",
        "vectorworks_capabilities": payload.get("style_manifest", {}),
        "execution_error": {
            "category": classification["category"],
            "summary": classification["summary"],
            "raw_traceback": error_text,
            "failed_line": "",
        },
        "artifacts": {
            "handoff_path": payload.get("_handoff_path", ""),
            "result_path": payload.get("execution_config", {}).get("resultPath", ""),
        },
        "retry_index": retry_index,
        "max_retries": max_retries,
    }


def _latest_fixer_payload(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    attempts = execution_result.get("attempts", [])
    if not isinstance(attempts, list):
        return {}
    for attempt in reversed(attempts):
        if not isinstance(attempt, dict):
            continue
        fixer_payload = attempt.get("fixer_payload")
        if isinstance(fixer_payload, dict):
            return fixer_payload
    return {}


def _remove_missing_style_calls(code: str, missing_style: str) -> str:
    lines = code.splitlines()
    filtered: List[str] = []
    removed = 0
    for line in lines:
        normalized = line.strip().lower()
        if (
            missing_style.lower() in line.lower()
            and "set_" in normalized
            and "_style(" in normalized
        ):
            removed += 1
            continue
        filtered.append(line)

    if removed:
        return "\n".join(filtered)
    return code


def _replace_with_available_style(
    code: str,
    missing_style: str,
    style_manifest: Dict[str, Any],
) -> str:
    replacement_order = (
        _normalize_style_list(style_manifest.get("slab_styles"))
        + _normalize_style_list(style_manifest.get("roof_styles"))
        + _normalize_style_list(style_manifest.get("wall_styles"))
    )
    for candidate in replacement_order:
        if candidate != missing_style:
            return code.replace(missing_style, candidate)
    return code


def _apply_heuristic_fix(
    code: str,
    error_text: str,
    classification: Dict[str, str],
    style_manifest: Dict[str, Any],
) -> Tuple[str, List[str]]:
    strategies: List[str] = []
    patched = code

    if classification["category"] == "resource_error":
        missing_style = _extract_missing_style(error_text)
        if missing_style:
            replaced = _replace_with_available_style(
                patched,
                missing_style,
                style_manifest,
            )
            if replaced != patched:
                patched = replaced
                strategies.append(
                    f"Replaced missing style '{missing_style}' with an available manifest style."
                )
            else:
                removed = _remove_missing_style_calls(patched, missing_style)
                if removed != patched:
                    patched = removed
                    strategies.append(
                        f"Removed explicit style assignment for missing style '{missing_style}'."
                    )

    return patched, strategies


def _attempt_execution(payload: Dict[str, Any], code: str) -> Dict[str, Any]:
    execution_summary = _execute_generated_code(payload, code)
    return {
        "ok": True,
        "execution_summary": execution_summary,
    }


def _run_with_retries(payload: Dict[str, Any], code: str) -> Dict[str, Any]:
    execution_config = payload.get("execution_config") or {}
    max_retries = int(execution_config.get("maxRetries", 2))
    style_manifest = payload.get("style_manifest", {}) or {}
    attempts: List[Dict[str, Any]] = []
    current_code = code

    for retry_index in range(0, max_retries + 1):
        try:
            attempt_result = _attempt_execution(payload, current_code)
            attempts.append(
                {
                    "attempt": retry_index + 1,
                    "status": "success",
                    "fix_applied": retry_index > 0,
                    "execution_summary": attempt_result["execution_summary"],
                }
            )
            return {
                "ok": True,
                "attempts": attempts,
                "final_code": attempt_result["execution_summary"].get(
                    "executed_code",
                    current_code,
                ),
                "execution_summary": attempt_result["execution_summary"],
            }
        except Exception as exc:
            error_text = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            classification = _classify_error(error_text)
            fixer_payload = _build_fixer_payload(
                payload,
                current_code,
                error_text,
                classification,
                retry_index + 1,
                max_retries + 1,
            )
            patched_code, strategies = _apply_heuristic_fix(
                current_code,
                error_text,
                classification,
                style_manifest,
            )
            attempts.append(
                {
                    "attempt": retry_index + 1,
                    "status": "failed",
                    "error": classification,
                    "raw_error": error_text,
                    "fixer_payload": fixer_payload,
                    "fix_strategies": strategies,
                }
            )

            if (
                retry_index >= max_retries
                or classification["category"]
                in {"environment_error", "configuration_error"}
                or patched_code == current_code
            ):
                return {
                    "ok": False,
                    "attempts": attempts,
                    "final_code": current_code,
                    "last_error": classification,
                    "last_error_traceback": error_text,
                }

            current_code = patched_code

    return {
        "ok": False,
        "attempts": attempts,
        "final_code": current_code,
        "last_error": {
            "category": "configuration_error",
            "summary": "Retry controller exited unexpectedly.",
        },
        "last_error_traceback": "",
    }


def run_handoff(handoff_path: str) -> dict:
    payload = _load_json(handoff_path)
    payload["_handoff_path"] = handoff_path
    project_root = payload.get("project_root") or os.environ.get(
        "OPENBIMFORGE_ROOT", ""
    )
    if not project_root:
        raise RuntimeError("Missing openBIMForge project root in handoff payload")

    os.environ["PROJECT_ROOT"] = project_root
    os.environ["OPENBIMFORGE_ROOT"] = project_root
    os.environ.setdefault(
        "OPENBIMFORGE_RUNTIME_ROOT",
        str(Path(project_root) / "forge_runtime"),
    )
    os.environ.setdefault(
        "OPENBIMFORGE_OUTPUT_ROOT",
        str(Path(project_root) / "forge_runtime" / "handoffs"),
    )
    os.environ["TEXT2BIM_PROJECT_ROOT"] = project_root
    os.environ.setdefault("TEXT2BIM_OUTPUT_ROOT", os.environ["OPENBIMFORGE_OUTPUT_ROOT"])
    _ensure_project_import_paths(str(project_root))

    execution_config = payload.get("execution_config") or {}
    orchestration_result = payload.get("orchestration_result") or {}
    code_result = str(
        payload.get("code_result", "")
        or orchestration_result.get("code_result", "")
        or ""
    )
    agent_output = str(
        payload.get("agent_output", "")
        or orchestration_result.get("agent_output", "")
        or ""
    )
    output_sum = str(
        payload.get("output_sum", "")
        or orchestration_result.get("output_sum", "")
        or ""
    )
    style_manifest = _effective_style_manifest(payload, str(project_root))
    payload["style_manifest"] = style_manifest

    manifest_path = execution_config.get("styleManifestPath") or os.environ.get(
        STYLE_MANIFEST_ENV,
        "",
    )
    if manifest_path:
        os.environ[STYLE_MANIFEST_ENV] = str(manifest_path)

    execution_result = _run_with_retries(payload, code_result)
    final_code = str(execution_result.get("final_code", "") or "")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = execution_config.get("jobName") or f"nexus_synthesis_{timestamp}"
    output_dir = _resolve_output_dir(payload)

    artifacts = {
        "prompt_path": str(output_dir / f"{stem}.prompt.txt"),
        "response_path": str(output_dir / f"{stem}.agents.txt"),
        "code_path": str(output_dir / f"{stem}.code.py"),
    }
    result_path = str(Path(execution_config.get("resultPath") or output_dir / f"{stem}.result.json").resolve())
    output_dir.mkdir(parents=True, exist_ok=True)
    Path(artifacts["prompt_path"]).write_text(
        str(payload.get("query", "")),
        encoding="utf-8",
    )
    Path(artifacts["response_path"]).write_text(
        output_sum,
        encoding="utf-8",
    )
    Path(artifacts["code_path"]).write_text(
        _strip_code_fences(final_code),
        encoding="utf-8",
    )

    export_summary = {}
    if execution_result.get("ok") and execution_config.get("exportArtifacts", True):
        export_summary = _export_vectorworks_artifacts(output_dir, stem)

    final = {
        "ok": bool(execution_result.get("ok")),
        "executed_in": "vectorworks",
        "handoff_path": handoff_path,
        "result": {
            "agent_output": agent_output,
            "output_sum": output_sum,
            "code_result": final_code,
            "execution_summary": execution_result.get("execution_summary", {}),
            "attempts": execution_result.get("attempts", []),
            "style_manifest": style_manifest,
        },
        "artifacts": {**artifacts, **export_summary},
    }

    if not execution_result.get("ok"):
        final["error"] = execution_result.get("last_error", {})
        final["error_traceback"] = execution_result.get("last_error_traceback", "")
        fixer_payload = _latest_fixer_payload(execution_result)
        fix_request_path = str(output_dir / f"{stem}.fix-request.json")
        fix_request = {
            "handoffPath": handoff_path,
            "resultPath": result_path,
            "fixApi": "/api/bim/forge-architect-fix",
            "note": "Nexus-Orchestrator: Repair the Constructor Synthesis Code and create a retry Transit-Payload.",
            "fixerPayload": fixer_payload,
        }
        _save_json(fix_request_path, fix_request)
        final["fixer"] = {
            "fix_request_path": fix_request_path,
            "fix_api": "/api/bim/forge-architect-fix",
            "next_step": "send fix_request_path or handoff/result paths to the Diagnostic Agent, then run the returned retry Transit-Payload in the Synthesis Workbench.",
        }

    pending_path = Path(f"{result_path}.pending.json")
    if pending_path.exists():
        try:
            pending_path.unlink()
        except OSError:
            pass

    _save_json(result_path, final)
    final["result_path"] = result_path
    return final


def build_run_summary(final: dict) -> str:
    artifacts = final.get("artifacts", {}) or {}
    error = final.get("error", {}) or {}
    lines = [
        "Nexus-Constructor synthesis cycle complete.",
        f"OK: {bool(final.get('ok'))}",
        f"Result JSON: {final.get('result_path', '')}",
        f"VWX: {artifacts.get('vwx_path', '')}",
        f"IFC ready: {bool(artifacts.get('ifc_ready'))}",
        f"IFC: {artifacts.get('ifc_path', '')}",
    ]
    if artifacts.get("ifc_status"):
        lines.append(f"IFC status: {artifacts.get('ifc_status')}")
    if artifacts.get("ifc_message"):
        lines.append(str(artifacts.get("ifc_message")))
    if error:
        lines.append(f"Error: {error.get('summary', error)}")
    return "\n".join(lines)


def run_handoff_with_dialog(handoff_path: str) -> dict:
    final = run_handoff(handoff_path)
    try:
        import vs  # type: ignore

        vs.AlrtDialog(build_run_summary(final))
    except Exception:
        print(build_run_summary(final))
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff-json", required=True)
    parser.add_argument("--result-json", required=False)
    args = parser.parse_args()

    final = run_handoff(args.handoff_json)
    if args.result_json:
        _save_json(args.result_json, final)
    else:
        print(json.dumps(final, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
