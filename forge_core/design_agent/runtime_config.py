import json
import os
from pathlib import Path
from typing import Any, Dict


_DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = os.environ.get(
    "OPENBIMFORGE_ROOT",
    os.environ.get("PROJECT_ROOT", str(_DEFAULT_PROJECT_ROOT)),
)

OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "openai-compatible",
    "ollama",
    "deepseek",
    "openrouter",
    "groq",
    "xai",
    "perplexity",
    "siliconflow",
    "together",
    "lmstudio",
    "vllm",
}


def _load_json_env(name: str) -> Dict[str, Any]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _env(primary: str, legacy: str = "", default: str = "") -> str:
    value = os.environ.get(primary, "")
    if value:
        return value
    if legacy:
        return os.environ.get(legacy, default)
    return default


def _normalize_provider(provider: str) -> str:
    value = (provider or "").strip().lower()
    aliases = {
        "anthropic": "claude",
        "vertexai": "gemini",
        "google": "gemini",
    }
    return aliases.get(value, value)


def _normalize_openai_base_url(provider: str, base_url: str) -> str:
    if not base_url:
        if provider == "ollama":
            return "http://127.0.0.1:11434/v1"
        return ""

    normalized = base_url.rstrip("/")
    if provider == "ollama":
        if normalized.endswith("/api"):
            return normalized[:-4] + "/v1"
        if not normalized.endswith("/v1"):
            return normalized + "/v1"
    return normalized


def get_unified_llm_config() -> Dict[str, Any]:
    config = _load_json_env("OPENBIMFORGE_LLM_CONFIG_JSON")
    if not config:
        config = _load_json_env("TEXT2BIM_LLM_CONFIG_JSON")
    if not config:
        config = {
            "provider": _env("OPENBIMFORGE_LLM_PROVIDER", "TEXT2BIM_LLM_PROVIDER"),
            "modelId": _env("OPENBIMFORGE_LLM_MODEL_ID", "TEXT2BIM_LLM_MODEL_ID"),
            "baseUrl": _env("OPENBIMFORGE_LLM_BASE_URL", "TEXT2BIM_LLM_BASE_URL"),
            "apiKey": _env("OPENBIMFORGE_LLM_API_KEY", "TEXT2BIM_LLM_API_KEY"),
            "vertexApiKey": _env("OPENBIMFORGE_VERTEX_API_KEY", "TEXT2BIM_VERTEX_API_KEY"),
        }

    provider = _normalize_provider(str(config.get("provider", "")))
    base_url = _normalize_openai_base_url(provider, str(config.get("baseUrl", "")))
    api_key = str(config.get("apiKey", "") or "")

    if provider == "ollama" and not api_key:
        api_key = "ollama"

    return {
        "provider": provider,
        "modelId": str(config.get("modelId", "") or ""),
        "baseUrl": base_url,
        "apiKey": api_key,
        "vertexApiKey": str(config.get("vertexApiKey", "") or ""),
    }


def get_runtime_workflow_model() -> str:
    config = get_unified_llm_config()
    provider = config.get("provider", "")
    if provider in OPENAI_COMPATIBLE_PROVIDERS and config.get("modelId"):
        return "unified_openai"
    if provider in {"claude", "gemini", "mistral"}:
        return provider
    return _env("OPENBIMFORGE_WORKFLOW_MODEL", "TEXT2BIM_WORKFLOW_MODEL", "unified_openai")


def get_execution_config() -> Dict[str, Any]:
    return {
        "executionMode": _env("OPENBIMFORGE_EXECUTION_MODE", "TEXT2BIM_EXECUTION_MODE", "vectorworks"),
        "solibriPath": _env(
            "OPENBIMFORGE_SOLIBRI_PATH",
            "TEXT2BIM_SOLIBRI_PATH",
            r"C:\Program Files\Solibri\SOLIBRI\Solibri.exe",
        ),
        "outputRoot": _env("OPENBIMFORGE_OUTPUT_ROOT", "TEXT2BIM_OUTPUT_ROOT"),
        "taskNumber": _env("OPENBIMFORGE_TASK_NUMBER", "TEXT2BIM_TASK_NUMBER", "Prompt_NR.1"),
        "taskRound": _env("OPENBIMFORGE_TASK_ROUND", "TEXT2BIM_TASK_ROUND", "1"),
    }
