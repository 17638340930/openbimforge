import os
import sys
import json
import traceback
from pathlib import Path
from datetime import datetime

# --- openBIMForge Import Probe START ---
def _write_probe(filename, data):
    try:
        runtime_root = Path(
            os.environ.get(
                "OPENBIMFORGE_RUNTIME_ROOT",
                str(Path(__file__).resolve().parents[2] / "forge_runtime"),
            )
        )
        probe_root = runtime_root / "handoffs"
        probe_root.mkdir(parents=True, exist_ok=True)
        probe_path = probe_root / filename
        with open(probe_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_import_probe_data = {
    "timestamp": datetime.now().isoformat(),
    "file": __file__ if "__file__" in globals() else "NOT_DEFINED",
    "cwd": os.getcwd(),
    "executable": sys.executable,
    "version": sys.version,
    "path": sys.path[:20],
}

# Define roots. JY: keep this copied bridge relocatable during the migration.
_OPENBIMFORGE_ROOT = Path(
    os.environ.get("OPENBIMFORGE_ROOT", str(Path(__file__).resolve().parents[2]))
)
_DESIGN_AGENT_ROOT = _OPENBIMFORGE_ROOT / "forge_core" / "design_agent"
_BUILD_AGENT_ROOT = _OPENBIMFORGE_ROOT / "forge_core" / "build_agent"

_import_probe_data.update({
    "new_root_exists": _OPENBIMFORGE_ROOT.exists(),
    "design_agent_exists": _DESIGN_AGENT_ROOT.exists(),
    "build_agent_exists": _BUILD_AGENT_ROOT.exists(),
})

# Self-healing injection
for _root in (
    _OPENBIMFORGE_ROOT,
    _OPENBIMFORGE_ROOT / "forge_core",
    _DESIGN_AGENT_ROOT,
    _BUILD_AGENT_ROOT,
):
    _root_str = str(_root)
    if _root_str not in sys.path:
        sys.path.insert(0, _root_str)

try:
    import tool_agent.multi_agents_workflow
    _import_probe_data["import_tool_agent"] = "success"
except Exception:
    _import_probe_data["import_tool_agent"] = "failed"
    _import_probe_data["traceback"] = traceback.format_exc()

_write_probe("openbimforge_vs_interface_import_probe.json", _import_probe_data)
# --- openBIMForge Import Probe END ---

import vs
import importlib
import json
import traceback
from datetime import datetime
try:
    import ptvsd
except Exception:
    ptvsd = None


def _load_legacy_workflow():
    # JY: Keep heavy old openBIMForge dependencies out of the openBIMForge runner path.
    import tool_agent.multi_agents_workflow as legacy_workflow
    importlib.reload(legacy_workflow)
    return legacy_workflow


class DebugServer:
    _instance = None

    @staticmethod
    def getInstance():
        if DebugServer._instance == None:
            DebugServer()
        return DebugServer._instance

    def __init__(self):
        if DebugServer._instance != None:
            raise Exception("This class is a singleton!")
        else:
            if ptvsd is None:
                raise RuntimeError("ptvsd is not installed; debug attach is unavailable.")
            DebugServer._instance = self
            svr_addr = str(ptvsd.options.host) + ":" + str(ptvsd.options.port)
            print(" -> Hosting debug server ... (" + svr_addr + ")")
            ptvsd.enable_attach()
            ptvsd.wait_for_attach(0.3)

# Below are the endpoints functions that will be excuted by the web palette backend

DEBUG = False
OPENBIMFORGE_RUN_ONCE_COMMAND = "__OPENBIMFORGE_RUN_ONCE__"


def get_nexus_framework_root():
    return Path(os.environ.get("OPENBIMFORGE_ROOT", str(Path(__file__).resolve().parents[2])))


def _openbimforge_runtime_root(project_root: Path):
    return Path(
        os.environ.get(
            "OPENBIMFORGE_RUNTIME_ROOT",
            str(project_root / "forge_runtime"),
        )
    )


def _run_openbimforge_once(payload_text=""):
    payload = {}
    if payload_text:
        try:
            payload = json.loads(payload_text)
        except Exception:
            payload = {}

    project_root = get_nexus_framework_root()
    runtime_root = _openbimforge_runtime_root(project_root)
    handoff_root = payload.get("handoffRoot") or str(runtime_root / "handoffs")
    payload_path = str(payload.get("payloadPath") or payload.get("handoffPath") or "").strip()
    handoff_root_path = Path(handoff_root)
    handoff_root_path.mkdir(parents=True, exist_ok=True)

    # JY: Leave a heartbeat so the Next console can prove the legacy VW bridge was reached.
    legacy_status_path = handoff_root_path / "openbimforge_legacy_bridge_status.json"

    def write_legacy_status(stage, extra=None):
        status = {
            "ok": stage not in ("failed", "exception"),
            "stage": stage,
            "bridge": "nexus_legacy_sync_bridge",
            "command": OPENBIMFORGE_RUN_ONCE_COMMAND,
            "handoffRoot": str(handoff_root_path),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        if extra:
            status.update(extra)
        try:
            legacy_status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    write_legacy_status("received", {"payloadKeys": sorted(payload.keys())})

    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    from forge_core.build_agent.vectorworks_execute import run_handoff
    from tool_agent_bridge.vectorworks_watch_runner import run_pending_handoffs

    write_legacy_status("runner_imported")
    if payload_path:
        target_path = Path(payload_path)
        write_legacy_status("running_exact", {"payloadPath": str(target_path)})
        results = [run_handoff(str(target_path))]
    else:
        results = run_pending_handoffs(str(handoff_root_path), once=True)
    summary = {
        "ok": True,
        "bridge": "nexus_legacy_sync_bridge",
        "command": OPENBIMFORGE_RUN_ONCE_COMMAND,
        "handoffRoot": str(handoff_root_path),
        "payloadPath": payload_path,
        "legacyStatusPath": str(legacy_status_path),
        "executedCount": len(results),
        "results": results,
    }
    write_legacy_status("completed", {"executedCount": len(results), "results": results})
    return json.dumps(summary, ensure_ascii=False, indent=2), ""


def excute_webpalette_po_coder(input_str, chat_history):
    # --- openBIMForge Call Probe START ---
    _call_probe_data = {
        "timestamp": datetime.now().isoformat(),
        "input_str": repr(input_str),
        "is_trigger": str(input_str).strip() == OPENBIMFORGE_RUN_ONCE_COMMAND,
        "chat_history_len": len(chat_history) if chat_history else 0,
        "path": sys.path[:20],
    }
    try:
        from tool_agent_bridge.vectorworks_watch_runner import run_pending_handoffs
        _call_probe_data["import_watch_runner"] = "success"
    except Exception:
        _call_probe_data["import_watch_runner"] = "failed"
        _call_probe_data["traceback"] = traceback.format_exc()
    _write_probe("openbimforge_vs_interface_call_probe.json", _call_probe_data)
    # --- openBIMForge Call Probe END ---

    # debug attach
    if DEBUG:
        DebugServer.getInstance()

    if str(input_str).strip() == OPENBIMFORGE_RUN_ONCE_COMMAND:
        try:
            return _run_openbimforge_once(str(chat_history))
        except Exception as exc:
            try:
                project_root = get_nexus_framework_root()
                handoff_root = _openbimforge_runtime_root(project_root) / "handoffs"
                handoff_root.mkdir(parents=True, exist_ok=True)
                status_path = handoff_root / "openbimforge_legacy_bridge_status.json"
                status_path.write_text(
                    json.dumps(
                        {
                            "ok": False,
                            "stage": "failed",
                            "bridge": "legacy_getAllPlantDataV2",
                            "command": OPENBIMFORGE_RUN_ONCE_COMMAND,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                            "updatedAt": datetime.now().isoformat(timespec="seconds"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
            error = {
                "ok": False,
                "bridge": "legacy_getAllPlantDataV2",
                "command": OPENBIMFORGE_RUN_ONCE_COMMAND,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            try:
                vs.AlrtDialog(
                    "Nexus Synthesis Node (Constructor) activation failed.\n"
                    f"{exc}\n\nReview the Nexus Framework logs or Script Errors for diagnostics."
                )
            except Exception:
                pass
            return json.dumps(error, ensure_ascii=False, indent=2), ""

    chat_history = chat_history.replace("\\n", "\n")
    legacy_workflow = _load_legacy_workflow()
    output_str, code_result = legacy_workflow.run_po_coder_agents(str(input_str), str(chat_history))
    
    return output_str, code_result

def excute_webpalette_export(output_str, issue_fixing_counter, chat_history, query):
    # debug attach
    if DEBUG:
        DebugServer.getInstance()

    chat_history = chat_history.replace("\\n", "\n")
    output_str = output_str.replace("\\n", "\n")
    legacy_workflow = _load_legacy_workflow()
    file_name = legacy_workflow.export_ifc_and_stuffs(str(output_str), int(issue_fixing_counter), str(chat_history), str(query))
    
    return file_name

def excute_webpalette_checking_loop(issue_fixing_counter, original_code_result, code_result, file_name):
    # debug attach
    if DEBUG:
        server = DebugServer.getInstance()
    code_result = code_result.replace("\\n", "\n")
    original_code_result = original_code_result.replace("\\n", "\n")
    legacy_workflow = _load_legacy_workflow()
    output_str, output_code_result = legacy_workflow.run_agent_checking_loop(int(issue_fixing_counter), str(original_code_result), str(code_result), str(file_name))

    return output_str, output_code_result

def excute_final_ifc_export(output_str, issue_fixing_counter):
    # debug attach
    if DEBUG:
        server = DebugServer.getInstance()
    output_str = output_str.replace("\\n", "\n")
    legacy_workflow = _load_legacy_workflow()
    file_name = legacy_workflow.export_final_ifc_and_checks(str(output_str), int(issue_fixing_counter))

    return file_name

def excute_pure_checking(file_name, issue_fixing_counter):
    # debug attach
    if DEBUG:
        server = DebugServer.getInstance()
    legacy_workflow = _load_legacy_workflow()
    legacy_workflow.pure_checking(str(file_name), int(issue_fixing_counter))

def excute_state_clean():
    # clean the content of state.json when reload the frontend page
    legacy_workflow = _load_legacy_workflow()
    with open(legacy_workflow.STATE_PATH, "w") as f:
        f.write("{}")


# BUG: This is not working with IFC output in Vectorworks as the geometry is not ready before output!
def faceless_execution(msg="Construct a residential building with a rectangular footprint (15m x 10m), a pitched roof and two floors. Create balconies by extending the floor slab outwards from the exterior walls on the first floor. Add doors and windows to each floor. Make sure that the balconies are accessible from the inside.", 
                       history="User: "):
    """
    BUG: This doesnt work with ifc output. as the geometry are not ready before output!
    """
    # Initial processing
    output_str, code_result = excute_webpalette_po_coder(msg, history)
    # final_output = output_str
    
    # Issue fixing loop (max 3 iterations)
    issue_fixing_counter = 0
    fix_code = code_result
    
    while issue_fixing_counter < 3:
        # Export step
        file_name = excute_webpalette_export(
            output_str, issue_fixing_counter, history, msg
        )
        
        if file_name in ("break", "", None):
            break
            
        # Checking loop step
        current_code = code_result if issue_fixing_counter == 0 else fix_code
        output_str2, fix_code = excute_webpalette_checking_loop(
            issue_fixing_counter, code_result, current_code, file_name
        )
        
        if output_str2 in ("break", "", None):
            break
            
        # Update for next iteration
        issue_fixing_counter += 1
        # final_output += output_str2
    
    # Final processing if all 3 iterations completed
    if issue_fixing_counter == 3:
        file_name_final = excute_final_ifc_export(output_str2, issue_fixing_counter)
        
        if file_name_final not in ("break", "", None):
            excute_pure_checking(file_name_final, issue_fixing_counter)
    
    excute_state_clean()

    final_output = "Execution completed successfully. Please check the output files and logs for details."
    vs.AlrtDialog(final_output)
    
    # return final_output
