import importlib
import json
import os
import math
import re
import time
import sys
from typing import Any, Dict, List

from openai import OpenAI

import tool_agent.vw_tools_extend
from tool_agent.agents import AVALIABLE_FUNCTIONS, FUNCTION_DESCRIPTION, OpenAiAgent
from tool_agent.runtime_config import PROJECT_ROOT
from tool_agent.utils import (
    remove_last_human_message_with_regex,
    safe_encode,
)
from tool_agent.vw_tools_extend import *  # noqa: F403

importlib.reload(tool_agent.vw_tools_extend)

DESIGN_AGENT_ROOT = os.path.join(PROJECT_ROOT, "forge_core", "design_agent")
RUNTIME_ROOT = os.environ.get(
    "OPENBIMFORGE_RUNTIME_ROOT",
    os.path.join(PROJECT_ROOT, "forge_runtime"),
)

PRODUCT_OWNER_PROMPT_PATH = os.path.join(
    DESIGN_AGENT_ROOT, "muti_agent_prompt", "po_chat_prompt_temp.txt"
)
CODER_PROMPT_PATH = os.path.join(
    DESIGN_AGENT_ROOT, "muti_agent_prompt", "coder_chat_prompt_temp.txt"
)
DEFAULT_STATE_PATH = os.path.join(RUNTIME_ROOT, "state", "default.json")
DEFAULT_STYLE_MANIFEST_PATH = os.path.join(
    RUNTIME_ROOT, "capabilities", "vectorworks_styles.json"
)
output_chunks: List[str] = []


def log_progress(message: str) -> None:
    """Internal log emittance for orchestration flow."""
    print(f"[Nexus-Orchestrator] {message}", file=sys.stderr, flush=True)


def _extract_forgevision_payload(query: str) -> Dict[str, Any]:
    match = re.search(
        r"【ForgeVisionConstraints】\s*(\{[\s\S]*?\})\s*【用户补充需求】",
        query or "",
    )
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except Exception:
        return {}


def _read_stl_bbox(stl_path: str) -> Dict[str, float]:
    if not stl_path or not os.path.exists(stl_path):
        return {}
    xs: List[float] = []
    ys: List[float] = []
    zs: List[float] = []
    vertex_pattern = re.compile(
        r"\bvertex\s+([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s+([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s+([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)",
        re.IGNORECASE,
    )
    with open(stl_path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            match = vertex_pattern.search(line)
            if not match:
                continue
            x, y, z = (float(match.group(index)) for index in (1, 2, 3))
            xs.append(x)
            ys.append(y)
            zs.append(z)
    if not xs:
        return {}
    return {
        "width": max(xs) - min(xs),
        "depth": max(ys) - min(ys),
        "height": max(zs) - min(zs),
    }


def _read_cad_vector_hint(cad_vector_path: str) -> Dict[str, Any]:
    if not cad_vector_path or not os.path.exists(cad_vector_path):
        return {}
    try:
        with open(cad_vector_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    vector = data.get("cad_vector") if isinstance(data, dict) else None
    if not isinstance(vector, list):
        return {}
    original_length = len(vector)
    max_vector_rows = 5000
    if original_length > max_vector_rows:
        vector = vector[:max_vector_rows]
    command_names = {
        "0": "line_or_point",
        "1": "arc_or_curve",
        "2": "circle_or_closed_profile",
        "3": "end_or_padding",
        "4": "sketch_profile_start",
        "5": "extrude_or_solid_operation",
    }
    command_counts: Dict[str, int] = {}
    xs: List[float] = []
    ys: List[float] = []
    extrusion_depth_tokens: List[float] = []
    raw_coordinates: List[Dict[str, float]] = []
    for row in vector:
        if not isinstance(row, list) or not row:
            continue
        command = str(row[0])
        command_counts[command] = command_counts.get(command, 0) + 1
        if len(row) > 2 and isinstance(row[1], (int, float)) and isinstance(row[2], (int, float)):
            if row[1] >= 0 and row[2] >= 0:
                x_value = float(row[1])
                y_value = float(row[2])
                xs.append(x_value)
                ys.append(y_value)
                if len(raw_coordinates) < 100:
                    raw_coordinates.append(
                        {
                            "x": round(x_value, 3),
                            "y": round(y_value, 3),
                        }
                    )
        if command == "5" and len(row) > 12 and isinstance(row[12], (int, float)) and row[12] >= 0:
            extrusion_depth_tokens.append(float(row[12]))
    named_counts = {
        command_names.get(command, f"command_{command}"): count
        for command, count in command_counts.items()
    }
    profile_count = command_counts.get("4", 0)
    extrusion_count = command_counts.get("5", 0)
    curve_count = command_counts.get("1", 0) + command_counts.get("2", 0)
    straight_count = command_counts.get("0", 0)
    complexity_score = min(
        100,
        straight_count * 2 + curve_count * 4 + extrusion_count * 8 + profile_count * 5,
    )
    hint: Dict[str, Any] = {
        "command_counts": command_counts,
        "named_command_counts": named_counts,
        "sequence_length": len(vector),
        "original_sequence_length": original_length,
        "is_sampled": original_length > max_vector_rows,
        "sample_limit": max_vector_rows,
        "profile_count": profile_count,
        "extrusion_count": extrusion_count,
        "curve_count": curve_count,
        "straight_segment_count": straight_count,
        "complexity_score": complexity_score,
        "raw_coordinates": raw_coordinates,
    }
    if xs and ys:
        normalized_width = max(xs) - min(xs)
        normalized_depth = max(ys) - min(ys)
        hint["normalized_width"] = normalized_width
        hint["normalized_depth"] = normalized_depth
        hint["normalized_aspect_ratio"] = round(
            max(normalized_width, normalized_depth) / max(min(normalized_width, normalized_depth), 1.0),
            2,
        )
    if extrusion_depth_tokens:
        hint["extrusion_depth_token_avg"] = round(sum(extrusion_depth_tokens) / len(extrusion_depth_tokens), 2)
        hint["extrusion_depth_token_max"] = max(extrusion_depth_tokens)
    if profile_count >= 3 or extrusion_count >= 3:
        hint["spatial_reading"] = "multi-volume stepped massing"
    elif curve_count >= 2:
        hint["spatial_reading"] = "curved or rounded footprint reference"
    elif straight_count >= 4:
        hint["spatial_reading"] = "orthogonal footprint reference"
    else:
        hint["spatial_reading"] = "simple massing reference"
    return hint


def _build_forgevision_context_hint(query: str) -> str:
    payload = _extract_forgevision_payload(query)
    if not payload:
        return ""

    constraints = payload.get("forgeVisionConstraints") or payload.get("constraints") or {}
    stl_paths = payload.get("stlPaths") or []
    cad_paths = payload.get("cadVectorPaths") or []
    stl_path = constraints.get("massingReferencePath") or (stl_paths[0] if stl_paths else "")
    cad_vector_path = constraints.get("cadVectorPath") or (cad_paths[0] if cad_paths else "")
    stl_bbox = _read_stl_bbox(stl_path)
    cad_hint = _read_cad_vector_hint(cad_vector_path)

    standard_floor_height_m = 3.6
    inferred_width_m = None
    inferred_depth_m = None
    inferred_height_m = None
    inferred_area_m2 = None
    inferred_storeys = None

    if stl_bbox:
        raw_width = max(stl_bbox.get("width", 0.0), stl_bbox.get("depth", 0.0))
        raw_depth = min(stl_bbox.get("width", 0.0), stl_bbox.get("depth", 0.0))
        raw_height = stl_bbox.get("height", 0.0)
        max_dimension = max(raw_width, raw_depth, raw_height)
        scale = 1.0
        if max_dimension > 1000:
            scale = 0.001
        elif max_dimension > 200:
            scale = 0.1
        elif raw_width and raw_width < 5:
            scale = 10.0
        inferred_width_m = max(raw_width * scale, 12.0) if raw_width else None
        inferred_depth_m = max(raw_depth * scale, 8.0) if raw_depth else None
        inferred_height_m = max(raw_height * scale, standard_floor_height_m) if raw_height else None
    elif cad_hint.get("normalized_width") and cad_hint.get("normalized_depth"):
        inferred_width_m = round(max(float(cad_hint["normalized_width"]) / 255.0 * 42.0, 12.0), 1)
        inferred_depth_m = round(max(float(cad_hint["normalized_depth"]) / 255.0 * 30.0, 8.0), 1)

    if inferred_width_m and inferred_depth_m:
        inferred_area_m2 = round(inferred_width_m * inferred_depth_m, 1)
    if inferred_height_m:
        inferred_storeys = max(1, int(math.ceil(inferred_height_m / standard_floor_height_m)))
    elif inferred_area_m2:
        inferred_storeys = max(1, min(8, int(math.ceil(inferred_area_m2 / 650.0))))
        inferred_height_m = round(inferred_storeys * standard_floor_height_m, 1)

    lines = [
        "",
        "ForgeVision-Form semantic context:",
        "- Treat ForgeVision outputs as reference-only massing evidence, not executable Vectorworks paths.",
        f"- cadVectorPath present: {bool(cad_vector_path)}",
        f"- STL massing present: {bool(stl_path)}",
        f"- CAD vector hint: {json.dumps(cad_hint, ensure_ascii=False)}",
        f"- Spatial vector reading: {cad_hint.get('spatial_reading', 'unavailable')}.",
        f"- Profile count: {cad_hint.get('profile_count', 0)}, extrusion count: {cad_hint.get('extrusion_count', 0)}, complexity score: {cad_hint.get('complexity_score', 0)}/100.",
        f"- CAD vector sampling: {cad_hint.get('sequence_length', 0)} of {cad_hint.get('original_sequence_length', 0)} rows analyzed.",
    ]
    raw_coordinates = cad_hint.get("raw_coordinates") or []
    if raw_coordinates:
        coordinate_text = ", ".join(
            f"({point.get('x')}, {point.get('y')})"
            for point in raw_coordinates[:100]
            if isinstance(point, dict)
        )
        lines.append(f"[CAD_COORDINATES] {coordinate_text}")
    if inferred_area_m2:
        lines.append(f"- Approximate footprint area from visual reference: {inferred_area_m2} m2.")
    if inferred_storeys:
        lines.append(f"- Approximate storey count from visual reference: {inferred_storeys} storeys.")
    if inferred_height_m:
        lines.append(f"- Approximate total massing height: {inferred_height_m} m, using 3.6 m standard floor height when unspecified.")
    lines.extend(
        [
            "- Architect-Agent must not report building type, area, or storey count as unknown when this context is present.",
            "- If user text omits storey count, infer storeys from STL height / 3.6 m; if height is unavailable, choose a plausible 2-8 storey count from footprint scale.",
            "- Convert the reference into a meaningful BIM concept: envelope, core, circulation, openings, floor plates, and program zones.",
            "- Preserve the visual massing character: orthogonal references should produce regular grids; curved references should use softened perimeter zones; multi-volume references should become stepped floor plates or podium/tower compositions.",
        ]
    )
    return "\n".join(lines)


def _get_forgevision_complexity_score(context_hint: str) -> int:
    if not context_hint:
        return 0
    match = re.search(r"complexity score:\s*(\d+)\s*/\s*100", context_hint, re.IGNORECASE)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def emit_stage_event(stage: Dict[str, Any]) -> None:
    """Emits Nexus-Stage events for real-time frontend monitoring."""
    print(
        f"[Nexus-Stage] {json.dumps(stage, ensure_ascii=False)}",
        file=sys.stderr,
        flush=True,
    )


def normalize_base_url(provider: str, base_url: str) -> str:
    normalized = (base_url or "").rstrip("/")
    if provider == "ollama":
        if normalized.endswith("/api"):
            return normalized[:-4] + "/v1"
        if normalized and not normalized.endswith("/v1"):
            return normalized + "/v1"
    return normalized


def _is_ollama_endpoint(provider: str, base_url: str) -> bool:
    return provider == "ollama" or "11434" in (base_url or "")


class UnifiedOpenAICompatibleAgent(OpenAiAgent):
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        chat_prompt_template=None,
        run_prompt_template=None,
        additional_tools=None,
    ):
        if not model:
            raise ValueError("Nexus unified runtime requires a modelId.")
        if not base_url:
            raise ValueError("Nexus unified runtime requires a baseUrl.")

        super().__init__(
            chat_prompt_template=chat_prompt_template,
            run_prompt_template=run_prompt_template,
            additional_tools=additional_tools,
        )
        
        import httpx
        client_kwargs = {
            "api_key": api_key or ("ollama" if _is_ollama_endpoint("", base_url) else ""),
            "timeout": httpx.Timeout(1800.0, connect=60.0),
            "http_client": httpx.Client(
                verify=False,
                http2=False,  # Force HTTP/1.1 to bypass proxy/TLS EOF drops
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
        }
        if base_url:
            client_kwargs["base_url"] = base_url
            
        self.client = OpenAI(**client_kwargs)
        self.model = model

    def generate_many(self, prompts, stop):
        return [self._chat_generate(prompt, stop) for prompt in prompts]

    def generate_one(self, prompt, stop):
        return self._chat_generate(prompt, stop)

    def _chat_generate(self, prompt, stop):
        result = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            stop=stop or None,
        )
        return result.choices[0].message.content

    def chat_with_function_call(self, task: str, chat_history: str, stop=["User:", "Programmer:", "Product Owner:"]):
        return super().chat_with_function_call(task, chat_history, stop=stop)

    def generate_with_function_call(
        self,
        prompt: str,
        stop: List[str],
        available_functions: Dict[str, Any],
        function_description: List[Dict[str, Any]],
    ):
        messages = [{"role": "user", "content": prompt}]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=function_description,
            tool_choice="auto",
        )
        response_message = response.choices[0].message
        tool_calls = getattr(response_message, "tool_calls", None)
        if not tool_calls:
            return response_message.content or ""

        messages.append(response_message)
        function_response = ""
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            if function_name not in available_functions:
                return self.generate_one(prompt, stop)

            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call.function.arguments or "{}")
            function_response = function_to_call(function_args.get("query", ""))
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "content": str(function_response),
                }
            )

        second_response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            stop=stop or None,
        )
        return second_response.choices[0].message.content


def init_vw_tools():
    return [
        CreateWallTool(),
        SetWallThickness(),
        SetWallHeight(),
        SetWallStyle(),
        GetWallElevation(),
        GetWallThickness(),
        AddWindowToWall(),
        AddDoorToWall(),
        Move(),
        DeleteTool(),
        FindSelect(),
        CreatePolygon(),
        GetPolygonVertex(),
        GetVertNum(),
        CreateSlab(),
        SetSlabHeight(),
        GetSlabHeight(),
        SetSlabStyle(),
        DuplicateObj(),
        RotateObj(),
        CreateRoof(),
        SetRoofAttributes(),
        SetRoofStyle(),
        CreateStoryLayer(),
        SetStoryLayerActive(),
        CreateSpace(),
    ]


def streamer(output: str):
    output_chunks.append(output)


def _capture_agent_output(agent: Any) -> None:
    agent.log = lambda message: output_chunks.append(str(message))


def clear_output():
    output_chunks.clear()


def get_output_sum() -> str:
    return "".join(output_chunks)


def _load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def _get_state_path() -> str:
    return os.environ.get("OPENBIMFORGE_STATE_PATH", DEFAULT_STATE_PATH)


def _load_state() -> Dict[str, Any]:
    state_path = _get_state_path()
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    if not os.path.exists(state_path):
        with open(state_path, "w", encoding="utf-8") as file:
            json.dump({}, file)

    try:
        with open(state_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    state_path = _get_state_path()
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as file:
        json.dump(state, file, default=safe_encode)


def _load_style_manifest() -> Dict[str, Any]:
    manifest_path = os.environ.get(
        "OPENBIMFORGE_STYLE_MANIFEST_PATH",
        DEFAULT_STYLE_MANIFEST_PATH,
    )
    if not os.path.exists(manifest_path):
        return {}
    try:
        with open(manifest_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def _build_style_manifest_hint(manifest: Dict[str, Any]) -> str:
    if not manifest:
        return ""

    lines = [
        "",
        "Vectorworks capability constraints:",
        "- Only use style names listed below.",
        "- If a style list is empty or a suitable style is missing, do not call the matching set_*_style tool.",
        "- Do not invent new Vectorworks style names.",
        "- Door/window symbols are environment dependent.",
        "- For slabs and roofs, use simple rectangle profiles in vertex order.",
    ]
    for key, label in [
        ("wall_styles", "Wall styles"),
        ("slab_styles", "Slab styles"),
        ("roof_styles", "Roof styles"),
        ("roof_slab_styles", "Roof slab styles"),
        ("door_symbols", "Door symbols"),
        ("window_symbols", "Window symbols"),
    ]:
        values = manifest.get(key, [])
        if values:
            lines.append(f"- {label}: {', '.join(str(value) for value in values)}")
        else:
            lines.append(f"- {label}: none available")
    
    return "\n".join(lines)


def create_unified_agent(provider: str, model_id: str, api_key: str, base_url: str, prompt: str, tool_list: list):
    """Creates the appropriate agent based on the provider, injecting custom HTTP clients for stability."""
    import httpx
    custom_http_client = httpx.Client(
        verify=False,
        http2=False,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    
    if provider == "anthropic" or "claude" in model_id.lower() or "mimo" in model_id.lower():
        from tool_agent.agents import ClaudeAgent
        import anthropic
        agent = ClaudeAgent(
            model=model_id,
            api_key=api_key or "sk-ant-dummy",
            chat_prompt_template=prompt,
            additional_tools=tool_list,
        )
        # Override client with base_url and custom http_client support
        agent.client = anthropic.Anthropic(
            api_key=api_key or "sk-ant-dummy",
            base_url=base_url if base_url else None,
            http_client=custom_http_client
        )
        return agent
    
    elif provider == "gemini" or "gemini" in model_id.lower():
        from tool_agent.agents import GeminiAgent
        return GeminiAgent(
            model=model_id,
            api_key=api_key,
            chat_prompt_template=prompt,
            additional_tools=tool_list,
        )
        
    elif provider == "mistral" or "mistral" in model_id.lower():
        from tool_agent.agents import MistralAgent
        return MistralAgent(
            model=model_id,
            api_key=api_key,
            chat_prompt_template=prompt,
            additional_tools=tool_list,
        )

    else:
        # Fallback to OpenAI compatible (Ollama, vLLM, DeepSeek, OpenAI)
        return UnifiedOpenAICompatibleAgent(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            chat_prompt_template=prompt,
            additional_tools=tool_list,
        )



def run_nexus_architect_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nexus Orchestration Entry Point: Coordinates the Semantic Logic Layer.
    """
    log_progress("Initializing Requirement Orchestration...")
    
    query = payload.get("query", "")
    forgevision_context_hint = _build_forgevision_context_hint(query)
    if forgevision_context_hint:
        query = f"{query}\n\n{forgevision_context_hint}"
    chat_history_front_end = payload.get("chat_history", "") # Normalized
    llm_config = payload.get("llm_config", {}) # Normalized
    
    provider = str(llm_config.get("provider", "")).lower()
    model_id = str(llm_config.get("modelId", "") or "")
    base_url = normalize_base_url(
        provider,
        str(llm_config.get("baseUrl", "") or ""),
    )
    api_key = str(
        llm_config.get("apiKey", "")
        or ("ollama" if _is_ollama_endpoint(provider, base_url) else "")
    )
    
    style_manifest = _load_style_manifest()
    style_manifest_hint = _build_style_manifest_hint(style_manifest)

    tool_list = init_vw_tools()
    po_prompt = _load_text(PRODUCT_OWNER_PROMPT_PATH)
    po_prompt += """

ForgeVision-Form interpretation rules:
- If ForgeVision-Form semantic context is present, use it as reference-only visual evidence.
- Never answer "unknown" for area/storey/building-scale fields when STL or cadVectorPath evidence is present; infer approximate values and explicitly mark them as approximate.
- If the user did not specify storey count, infer it from STL total height divided by 3.6 m standard floor height. If no STL height exists, infer a plausible 2-8 storey count from footprint scale and program.
- Enrich the architecture: define program zones, vertical core, floor plates, facade rhythm, openings, circulation, and roof/MEP massing instead of producing a plain white block.
"""
    coder_prompt = _load_text(CODER_PROMPT_PATH)
    coder_prompt += """

Python correctness constraints:
- Generated code must be valid Python 3 and must not rely on syntax that has not been tested mentally.
- When iterating nested coordinate pairs with enumerate, always unpack as:
  for i, ((x1, y1), (x2, y2)) in enumerate(pairs):
  Never write: for i, (x1, y1), (x2, y2) in enumerate(pairs)
- Prefer assigning tuple items explicitly when unsure:
  for i, segment in enumerate(pairs):
      (x1, y1), (x2, y2) = segment
- Do not include local Windows file paths from ForgeVision constraints in Vectorworks executable code; use them only as reference context.
- When ForgeVision vector context is present, translate it into native BIM primitives:
  - profile_count/extrusion_count imply massing hierarchy and floor-plate variation.
  - normalized_aspect_ratio guides rectangular footprint proportions.
  - spatial_reading guides facade rhythm, core placement, openings, and podium/tower composition.
- Avoid plain white-box output: include storeys, slabs, perimeter walls, a vertical circulation/core zone, roof/MEP massing, facade openings, and at least one program-zone distinction when scale allows.
- Based on complexity_score, generate at least one interior vertical core (stair/elevator shaft) and distinct facade window patterns when the score is above 40.
- When spatial_reading is "multi-volume stepped massing", generated Vectorworks code must include layered floor-plate logic with native slab creation and wall creation loops; prefer vs.CreateSlab / slab helper calls and vs.Wall / wall helper calls over mesh-like proxy geometry.
- If vector data is ambiguous, prefer a clean schematic BIM interpretation over copying mesh-like geometry.
"""

    execution_mode = os.environ.get("OPENBIMFORGE_EXECUTION_MODE", "vectorworks")
    return_code_only = True

    log_progress(f"Activating Nexus-Architect with model: {model_id}")
    log_progress(f"[Diagnostics] Provider: {provider} | BaseURL: {base_url} | API Key length: {len(api_key)}")
    log_progress(f"[Diagnostics] Execution Mode: {execution_mode} | Return Code Only: {return_code_only}")

    log_progress("Creating Architect-Agent client...")
    agent_po = create_unified_agent(
        provider=provider,
        model_id=model_id,
        api_key=api_key,
        base_url=base_url,
        prompt=po_prompt,
        tool_list=tool_list,
    )
    log_progress("Architect-Agent client ready.")
    log_progress("Creating Constructor-Agent client...")
    agent_coder = create_unified_agent(
        provider=provider,
        model_id=model_id,
        api_key=api_key,
        base_url=base_url,
        prompt=coder_prompt,
        tool_list=tool_list,
    )
    log_progress("Constructor-Agent client ready.")
    agent_po.set_stream(streamer)
    agent_coder.set_stream(streamer)
    _capture_agent_output(agent_po)
    _capture_agent_output(agent_coder)
    clear_output()

    previous_state = _load_state()
    chat_history = remove_last_human_message_with_regex(chat_history_front_end)

    stage_events: List[Dict[str, Any]] = []

    # Stage 1: Architect (Logic)
    from forge_core.build_agent.adapter_entry import print_stage_header, extract_semantic_slots
    print_stage_header(1, "ARCHITECT-AGENT (需求规划)")
    print(">> 状态: 正在调用主模型分析语义...", file=sys.stderr, flush=True)

    po_started = time.perf_counter()
    emit_stage_event(
        {
            "id": "architect_agent",
            "label": "Architect-Agent (需求规划)",
            "status": "running",
            "detail": "Executing Semantic Logic Orchestration...",
        }
    )
    
    log_progress("Architect-Agent model request started.")
    answer = agent_po.chat_with_function_call(query, chat_history)
    log_progress("Architect-Agent model request completed.")
    
    if "Error:" in answer:
        log_progress(f"Critical error in Orchestration stage: {answer}")
        raise RuntimeError(f"Workflow aborted due to logic error: {answer}")

    slots = extract_semantic_slots(answer)
    query_slots = extract_semantic_slots(query)
    slots = {
        "building_type": slots.get("building_type") or query_slots.get("building_type"),
        "storey_count": slots.get("storey_count") or query_slots.get("storey_count"),
        "target_area_m2": slots.get("target_area_m2") or query_slots.get("target_area_m2"),
        "floor_height_m": slots.get("floor_height_m") or query_slots.get("floor_height_m"),
        "structure_system": slots.get("structure_system") or query_slots.get("structure_system"),
    }
    building_type = slots.get("building_type") or "未知建筑"
    area = slots.get("target_area_m2") or "未知"
    floors = slots.get("storey_count") or "未知"
    print(f">> 总结: 已识别为 [{building_type}]，目标面积 [{area}平]，层数 [{floors}层]。", file=sys.stderr, flush=True)

    po_duration_s = round(time.perf_counter() - po_started, 1)
    print(f"[✓] 阶段耗时: {po_duration_s}s", file=sys.stderr, flush=True)
    po_duration_ms = po_duration_s * 1000
    po_event = {
        "id": "architect_agent",
        "label": "Architect-Agent (需求规划)",
        "status": "completed",
        "duration_ms": po_duration_ms,
        "detail": "Semantic logic orchestration successfully synthesized.",
    }
    stage_events.append(po_event)
    emit_stage_event(po_event)

    # Stage 2: Constructor (Code)
    print_stage_header(2, "CONSTRUCTOR-AGENT (物理合成)")
    print(">> 状态: 正在生成 Vectorworks Python 核心脚本...", file=sys.stderr, flush=True)
    coder_started = time.perf_counter()
    emit_stage_event(
        {
            "id": "constructor_agent",
            "label": "Constructor-Agent (物理构筑)",
            "status": "running",
            "detail": "Synthesizing Automated Constructive code...",
        }
    )
    
    log_progress("Constructor-Agent model request started.")
    constructor_input = answer
    if forgevision_context_hint:
        constructor_input = (
            f"{answer}\n\n"
            "[Constructor ForgeVision reference]\n"
            f"{forgevision_context_hint}\n"
            "Use the vector reading to create semantic Vectorworks BIM elements, not raw imported mesh geometry."
        )
        if _get_forgevision_complexity_score(forgevision_context_hint) > 10:
            print(">> 状态: 正在执行 [高精度矢量模式] 合成...", file=sys.stderr, flush=True)
            cad_instruction = (
                "\n[CRITICAL: VECTOR-DRIVEN SYNTHESIS]\n"
                "The current task is flagged as HIGH-PRECISION. You MUST use the provided [CAD_COORDINATES] "
                "to define building footprints and wall segments. DO NOT rely on the STL mesh for footprint details. "
                "Use vs.BeginPoly(), vs.AddPoint(), and vs.EndPoly() to ensure geometric fidelity. "
                "If exact Vectorworks polygon APIs are unavailable in the helper layer, create equivalent native polygon/slab footprints "
                "from the coordinate sequence and then generate walls along those segments.\n"
            )
            constructor_input = cad_instruction + constructor_input

    state, code_result = agent_coder.chat(
        constructor_input,
        chat_history, # Use consistent history
        return_code=return_code_only,
        **previous_state,
    )
    log_progress("Constructor-Agent model request completed.")
    
    lines_count = len(code_result.split("\n")) if code_result else 0
    print(f">> 规模: 已生成 {lines_count} 行构筑指令代码。", file=sys.stderr, flush=True)
    coder_duration_s = round(time.perf_counter() - coder_started, 1)
    print(f"[✓] 阶段耗时: {coder_duration_s}s", file=sys.stderr, flush=True)
    coder_duration_ms = coder_duration_s * 1000
    coder_event = {
        "id": "constructor_agent",
        "label": "Constructor-Agent (物理构筑)",
        "status": "completed",
        "duration_ms": coder_duration_ms,
        "detail": "Constructive synthesis logic generated.",
    }
    stage_events.append(coder_event)
    emit_stage_event(coder_event)

    # Stage 3: Persistence
    if isinstance(state, dict):
        previous_state.update(state)
    _save_state(previous_state)
    
    output_sum = get_output_sum()

    return {
        "ok": True,
        "agent_output": answer,
        "output_sum": output_sum,
        "code_result": code_result,
        "stage_events": stage_events,
        "state_path": _get_state_path(),
        "model_used": model_id,
        "provider_used": provider,
        "execution_mode": execution_mode,
        "style_manifest": style_manifest,
    }
