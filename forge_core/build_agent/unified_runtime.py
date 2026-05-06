import importlib
import json
import os
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
    coder_prompt = _load_text(CODER_PROMPT_PATH)

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
    state, code_result = agent_coder.chat(
        answer,
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
