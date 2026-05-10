"""
openBIMForge Vectorworks module shim.

This file intentionally lives at the project root so that external Python
processes (the Nexus bridge, MEP pipeline, CLI tools, unit tests) can run
``import vs`` outside the Vectorworks VM. The mock exports match the real
`vs.*` surface area used by the Constructor-Agent (see
``forge_core/design_agent/vs.py`` for the full signature stubs).

Do NOT delete. The file is required for all external tooling; when the
code actually runs inside the Vectorworks VM, VW's built-in `vs` module
takes precedence.
"""
import os
import sys

# Ensure the mock is findable
try:
    from forge_core.design_agent.vs import *  # noqa: F401,F403
except ImportError:
    # Fallback if pathing is weird
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from forge_core.design_agent.vs import *  # noqa: F401,F403
