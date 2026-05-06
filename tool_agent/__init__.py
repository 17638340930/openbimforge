"""Compatibility shim for legacy internal imports.

Author: JY

The public openBIMForge structure uses `forge_core/design_agent`.
Some migrated modules still import `tool_agent.*`; keep those imports
working while the package is gradually renamed.
"""

from pathlib import Path

_design_agent = Path(__file__).resolve().parents[1] / "forge_core" / "design_agent"
__path__ = [str(_design_agent)]

