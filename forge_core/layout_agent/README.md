# Layout Agent

This module owns openBIMForge's image/sketch-to-CAD layout workflow.

Planned responsibilities:

- Convert image references and design intent into CAD/layout candidates.
- Prepare STL, preview, and layout artifacts for downstream review.
- Expose a clean interface to the Design Agent and Build Agent.
- Keep third-party model/runtime details behind an adapter boundary.