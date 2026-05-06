import argparse
import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime
import traceback


def log_progress(message: str) -> None:
    """Detailed CMD logging for framework diagnostics, but only for business logic."""
    # Filter out heartbeats or noise if they somehow enter here
    if "/api/chat" in message or "POST " in message:
        return
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [Nexus] {message}", file=sys.stderr, flush=True)


def print_stage_header(stage_num: int, label: str) -> None:
    """Prints a clear, high-visibility stage boundary for PowerShell."""
    border = "-" * 70
    print(f"\n{border}", file=sys.stderr, flush=True)
    print(f"[STAGE {stage_num}/4] {label.upper()}", file=sys.stderr, flush=True)


def emit_stage_event(stage: dict) -> None:
    """Emits structured stage events for frontend progress tracking."""
    print(
        f"[Nexus-Stage] {json.dumps(stage, ensure_ascii=False)}",
        file=sys.stderr,
        flush=True,
    )


def parse_payload(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sanitize_session_id(session_id: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]", "_", session_id.strip())
    return value[:120] if value else "default"


def resolve_state_path(project_root: str, payload: dict) -> str:
    runtime_root = os.environ.get(
        "OPENBIMFORGE_RUNTIME_ROOT",
        os.path.join(project_root, "forge_runtime"),
    )
    state_root = os.path.join(runtime_root, "state")
    session_id = str(payload.get("session_id", "") or "").strip()
    if not session_id:
        return os.path.join(state_root, "default_nexus_state.json")

    safe_session_id = sanitize_session_id(session_id)
    return os.path.join(state_root, f"{safe_session_id}.json")


def extract_semantic_slots(text: str) -> dict:
    floor_match = re.search(r"(\d+)\s*(层|楼|floors?|storeys?)", text, re.IGNORECASE)
    area_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(㎡|m2|m²|square meters?)", text, re.IGNORECASE
    )
    height_match = re.search(
        r"(层高|净高|floor height|storey height)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(m|米|meter|meters)",
        text,
        re.IGNORECASE,
    )

    building_type = None
    for token in [
        "办公楼", "住宅", "公寓", "医院", "学校",
        "office", "residential", "apartment", "hospital", "school",
    ]:
        if re.search(token, text, re.IGNORECASE):
            building_type = token
            break

    return {
        "building_type": building_type,
        "storey_count": int(floor_match.group(1)) if floor_match else None,
        "target_area_m2": float(area_match.group(1)) if area_match else None,
        "floor_height_m": float(height_match.group(2)) if height_match else None,
    }


def make_unified_bim_json(payload: dict, slots: dict, mode: str) -> dict:
    return {
        "schema_version": "Nexus-BIM-JSON 1.0",
        "source": {"pipeline": "nexus-architect", "mode": mode},
        "requirements": {
            "query": payload.get("query", ""),
            "chat_history": payload.get("chat_history", ""),
        },
        "semantic_slots": slots,
        "generation": {
            "status": "draft",
            "next_step": "constructive_synthesis",
            "adapter_note": "Nexus-Architect synthesized logic. Final Digital Assets require Constructive Synthesis.",
        },
    }


def prepare_nexus_transit_payload(payload: dict, generation_result: dict) -> dict:
    """Prepares the Transit-Payload for the Nexus Synthesis Node."""
    project_root = os.environ.get("OPENBIMFORGE_ROOT", "")
    runtime_root = os.environ.get(
        "OPENBIMFORGE_RUNTIME_ROOT",
        os.path.join(project_root, "forge_runtime"),
    )
    execution_config = payload.get("execution_config") or {}
    
    handoff_root = execution_config.get("outputRoot") or os.path.join(
        runtime_root,
        "handoffs",
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    handoff_dir = Path(handoff_root)
    handoff_dir.mkdir(parents=True, exist_ok=True)
    
    session_id = sanitize_session_id(str(payload.get("session_id", "") or "session"))
    run_stem = f"nexus_payload_{session_id[:16]}_{timestamp}"
    handoff_path = (handoff_dir / f"{run_stem}.json").resolve()
    result_path = (handoff_dir / f"{run_stem}.result.json").resolve()
    
    runner_script = (
        Path(project_root) / "forge_core" / "build_agent" / "vectorworks_execute.py"
    )
    
    transit_payload = {
        "framework": "Nexus Multi-Agent Orchestration",
        "project_root": project_root,
        "query": payload.get("query", ""),
        "chat_history": payload.get("chat_history", ""),
        "llm_config": payload.get("llm_config") or {},
        "orchestration_result": {
            "agent_output": generation_result.get("agent_output", ""),
            "code_result": generation_result.get("code_result", ""),
            "output_sum": generation_result.get("output_sum", ""),
            "state_path": generation_result.get("state_path", ""),
            "model_used": generation_result.get("model_used", ""),
        },
        "agent_output": generation_result.get("agent_output", ""),
        "code_result": generation_result.get("code_result", ""),
        "output_sum": generation_result.get("output_sum", ""),
        "execution_config": {
            **execution_config,
            "resultPath": str(result_path),
        },
    }
    
    handoff_path.write_text(
        json.dumps(transit_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    log_progress(f"Transit-Payload synthesized: {handoff_path.name}")
    
    stage_events = list(generation_result.get("stage_events", []))
    stage_events.extend(
        [
            {
                "id": "transit_payload",
                "label": "Transit-Payload (载荷交付)",
                "status": "completed",
                "detail": f"Payload delivered to {handoff_path.name}",
            },
            {
                "id": "nexus_execute",
                "label": "Nexus-Execute (物理构筑)",
                "status": "waiting",
                "detail": "Synthesis Node is polling for the Transit-Payload.",
            },
        ]
    )

    return {
        "handoff_path": str(handoff_path),
        "result_path": str(result_path),
        "runner_script": str(runner_script),
        "next_step": "nexus_constructive_synthesis",
        "agent_output": generation_result.get("agent_output", ""),
        "code_result": generation_result.get("code_result", ""),
        "output_sum": generation_result.get("output_sum", ""),
        "stage_events": stage_events,
        "state_path": generation_result.get("state_path", ""),
        "model_used": generation_result.get("model_used", ""),
        "execution_mode": "vectorworks",
    }


def run_nexus_live_orchestration(payload: dict) -> dict:
    project_root = os.environ.get("OPENBIMFORGE_ROOT", "")
    query = payload.get("query", "")
    chat_history = payload.get("chat_history", "")
    llm_config = payload.get("llm_config") or {}
    execution_config = payload.get("execution_config") or {}
    execution_mode = str(execution_config.get("executionMode") or "dry-run")

    if not project_root:
        raise RuntimeError("OPENBIMFORGE_ROOT environment variable is missing.")

    log_progress(f"协同编排任务启动 | Mode: {execution_mode} | Model: {llm_config.get('modelId', 'default')}")
    
    llm_config_json = json.dumps(llm_config)
    os.environ["OPENBIMFORGE_LLM_CONFIG_JSON"] = llm_config_json
    # Deprecated compatibility aliases for legacy Text2BIM modules and old Vectorworks .vlb shims.
    # Keep until the Vectorworks plugin is rebuilt without TEXT2BIM_* lookups.
    os.environ["TEXT2BIM_LLM_CONFIG_JSON"] = llm_config_json
    os.environ["OPENBIMFORGE_STATE_PATH"] = resolve_state_path(project_root, payload)
    os.environ["OPENBIMFORGE_EXECUTION_MODE"] = execution_mode
    os.environ["TEXT2BIM_EXECUTION_MODE"] = execution_mode
    
    if execution_config.get("outputRoot"):
        os.environ["OPENBIMFORGE_OUTPUT_ROOT"] = str(execution_config["outputRoot"])
        os.environ["TEXT2BIM_OUTPUT_ROOT"] = str(execution_config["outputRoot"])

    log_progress("Loading Nexus runtime module...")
    sys.path.insert(0, project_root)
    from forge_core.build_agent.unified_runtime import run_nexus_architect_pipeline
    log_progress("Nexus runtime module loaded.")
    
    # [1/4 & 2/4] Synthesis are handled inside run_nexus_architect_pipeline
    log_progress("Entering Nexus architect pipeline...")
    generation_result = run_nexus_architect_pipeline(payload)
    log_progress("Nexus architect pipeline returned.")
    
    if not generation_result.get("ok"):
        log_progress(f"!! CRITICAL ERROR: {generation_result.get('error')}")
        return generation_result

    # [3/4] Transit
    print_stage_header(3, "TRANSIT-PAYLOAD (载荷交付)")
    print(">> 状态: 正在封包 Transit-Payload...", file=sys.stderr, flush=True)
    transit_data = prepare_nexus_transit_payload(payload, generation_result)
    handoff_name = Path(transit_data['handoff_path']).name
    print(f">> 存储: forge_runtime\\handoffs\\{handoff_name}", file=sys.stderr, flush=True)
    print("[✓] 状态: 交付就绪", file=sys.stderr, flush=True)
    
    # [4/4] Execute
    if execution_mode == "vectorworks":
        print_stage_header(4, "NEXUS-EXECUTE (物理构筑)")
        print(">> 状态: Transit-Payload 已排队，等待 Vectorworks Web Palette / VM 拉取执行...", file=sys.stderr, flush=True)
        print(">> 说明: 外部 Python 进程不执行 vs.*，避免生成伪 .result.json 阻断 VM。", file=sys.stderr, flush=True)
        emit_stage_event({
            "id": "nexus_execute",
            "label": "Nexus-Execute (物理构筑)",
            "status": "waiting",
            "detail": "Transit-Payload queued. Waiting for Vectorworks VM execution."
        })
        transit_data["summary_note"] = "Transit-Payload queued. Waiting for Vectorworks VM execution."
    else:
        # Dry-run
        log_progress(">> DRY-RUN: Skipping physical execution.")
        emit_stage_event({
            "id": "nexus_execute",
            "label": "Nexus-Execute (物理构筑)",
            "status": "completed",
            "detail": "Dry-run complete."
        })

    log_progress("Nexus Task Finished Successfully.")
    return transit_data


def main() -> int:
    try:
        parser = argparse.ArgumentParser(description="Nexus Multi-Agent Orchestration Adapter")
        parser.add_argument("--payload-json", required=True, help="Path to the orchestration payload")
        args = parser.parse_args()

        payload = parse_payload(args.payload_json)
        # Ensure we use 'live' mode if it's coming from the architect adapter
        mode = payload.get("mode", "live") 
        query = payload.get("query", "")
        merged_text = f"{query}\n{payload.get('chat_history', '')}"
        
        log_progress("Parsing semantic requirements...")
        slots = extract_semantic_slots(merged_text)
        unified = make_unified_bim_json(payload, slots, mode)

        diagnostics = {
            "nexus_root": os.environ.get("OPENBIMFORGE_ROOT", ""),
            "orchestration_strategy": "unified_nexus_pipeline",
        }

        if mode == "live":
            try:
                live_result = run_nexus_live_orchestration(payload)
                diagnostics["orchestration_status"] = "success"
                
                final_result = {
                    "ok": live_result.get("ok", True),
                    "mode": "live",
                    "unified_bim_json": unified,
                    "diagnostics": diagnostics,
                    "live": live_result,
                }
                print(json.dumps(final_result, ensure_ascii=False))
                return 0
            except Exception as e:
                diagnostics["orchestration_status"] = "failed"
                diagnostics["error"] = str(e)
                log_progress(f"Orchestration fatal error: {e}")
                traceback.print_exc(file=sys.stderr)
                
                error_result = {
                    "ok": False,
                    "mode": "live",
                    "unified_bim_json": unified,
                    "diagnostics": diagnostics,
                }
                print(json.dumps(error_result, ensure_ascii=False))
                return 0

        # Mock fallback (should be rare in live usage)
        result = {
            "ok": True,
            "mode": "mock",
            "unified_bim_json": unified,
            "diagnostics": diagnostics,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
        
    except Exception as e:
        log_progress(f"Critical Adapter Failure: {e}")
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
