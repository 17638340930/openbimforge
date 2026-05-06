"""
openBIMForge Compatibility Shim
Redirects 'import vs' to the mock implementation in forge_core.
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
