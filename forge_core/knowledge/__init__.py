"""
openBIMForge Knowledge Pack.

This module provides typology-driven architectural knowledge that is injected
into the Nexus Architect/Constructor prompts at pipeline time. It replaces the
previous hard-coded defaults (e.g. `3.6 m floor height`) with structured, editable
parameters keyed by building type.

The knowledge pack is intentionally *not* a RAG system. Because all lookups are
deterministic (keyed by `building_type`), a simple JSON + loader is more
reliable and diagnosable than embedding-based retrieval.

Public entry points:
    - `load_typology(building_type)` returns the typology record for a building
      type, falling back to the generic default when unknown.
    - `build_typology_prompt_hint(building_type)` renders the typology as a
      prompt block suitable for direct injection into the Architect / Constructor
      prompts.
    - `resolve_default(building_type, key, user_value)` returns `user_value` if
      provided, otherwise falls back to the typology default.
"""

from .loader import (
    build_typology_prompt_hint,
    get_available_typologies,
    load_typology,
    resolve_default,
)

__all__ = [
    "build_typology_prompt_hint",
    "get_available_typologies",
    "load_typology",
    "resolve_default",
]
