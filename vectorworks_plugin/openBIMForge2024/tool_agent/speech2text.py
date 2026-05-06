import importlib.util
import sys
from pathlib import Path

# JY: Compatibility proxy for legacy .vlb speech bridge imports.
OPENBIMFORGE_ROOT = Path(__file__).resolve().parents[3]
REAL_SPEECH2TEXT = OPENBIMFORGE_ROOT / "tool_agent" / "speech2text.py"

_root_str = str(OPENBIMFORGE_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

_spec = importlib.util.spec_from_file_location("_openbimforge_real_speech2text", REAL_SPEECH2TEXT)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load real speech2text from {REAL_SPEECH2TEXT}")

_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

for _name in dir(_module):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_module, _name)
