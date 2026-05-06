"""Compatibility shim for legacy build-agent imports.

Author: JY

The public openBIMForge structure uses `forge_core/build_agent`.
Some migrated modules still import `tool_agent_bridge.*`; keep those
imports working while the package is gradually renamed.
"""

from pathlib import Path

_build_agent = Path(__file__).resolve().parents[1] / "forge_core" / "build_agent"
__path__ = [str(_build_agent)]

