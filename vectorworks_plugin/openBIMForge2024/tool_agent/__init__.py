import sys
from pathlib import Path

# JY: Vectorworks .vlb imports `tool_agent.vs_interface` before our normal
# project roots are on sys.path. This shim package lives beside the .vlb and
# extends imports back to the real openBIMForge sources.
OPENBIMFORGE_ROOT = Path(__file__).resolve().parents[3]
OPENBIMFORGE_CORE_ROOT = OPENBIMFORGE_ROOT / "forge_core"
REAL_TOOL_AGENT_ROOT = OPENBIMFORGE_CORE_ROOT / "design_agent"

for _path in (OPENBIMFORGE_ROOT, OPENBIMFORGE_CORE_ROOT):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

_real_tool_agent_path = str(REAL_TOOL_AGENT_ROOT)
if _real_tool_agent_path not in __path__:
    __path__.append(_real_tool_agent_path)
