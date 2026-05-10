"""
Emits a Vectorworks Python snippet that rebuilds the MEP plan inside the
active document. The snippet draws each pipe segment as a cylinder extrusion
using `vs.Cone3D` / `vs.Rotate3D` / `vs.Move3D` primitives that are
available in the stock VW 2024 Python VM.

The generated script mirrors the style of the existing
`vectorworks_execute.py` snippets so it can be injected into the same
Transit-Payload pipeline.
"""

from __future__ import annotations

import math
from typing import List

from .schema import MepPlan, PipeSegment


def _cylinder_snippet(seg: PipeSegment) -> str:
    sx, sy, sz = seg.start
    ex, ey, ez = seg.end
    length = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2 + (ez - sz) ** 2)
    if length < 1e-3:
        return ""
    # Tube radius in millimetres; VS accepts mm.
    radius = seg.diameter_mm / 2.0

    # Direction of the segment.
    dx, dy, dz = ex - sx, ey - sy, ez - sz

    # Rotation: we need to align the cylinder's default axis (Z) with the
    # segment direction. Compute the rotation angle in XY plane and the
    # inclination from vertical.
    horizontal_len = math.sqrt(dx * dx + dy * dy)
    yaw_deg = math.degrees(math.atan2(dy, dx))
    pitch_deg = math.degrees(math.atan2(horizontal_len, dz))

    return (
        f"\n# {seg.id}\n"
        f"vs.BeginXtrd(0, {length:.3f})\n"
        f"vs.Oval(-{radius:.3f}, -{radius:.3f}, {radius:.3f}, {radius:.3f})\n"
        f"vs.EndXtrd()\n"
        f"tube_{seg.id.replace('-', '_')} = vs.LNewObj()\n"
        f"vs.SetRot3D(tube_{seg.id.replace('-', '_')}, {pitch_deg:.3f}, 0, 0, {sx:.3f}, {sy:.3f}, {sz:.3f})\n"
        f"vs.SetRot3D(tube_{seg.id.replace('-', '_')}, 0, 0, {yaw_deg:.3f}, {sx:.3f}, {sy:.3f}, {sz:.3f})\n"
        f"vs.Move3DObj(tube_{seg.id.replace('-', '_')}, {sx:.3f}, {sy:.3f}, {sz:.3f})\n"
    )


def generate_vectorworks_script(plan: MepPlan) -> str:
    lines: List[str] = [
        "# openBIMForge MEP script - sanitary drainage only",
        "import vs",
        "",
        "# Create a dedicated class for MEP so the layer can be hidden easily.",
        "vs.NameClass('openBIMForge-MEP-Drainage')",
        "",
    ]
    for seg in plan.pipes:
        snippet = _cylinder_snippet(seg)
        if snippet:
            lines.append(snippet)
    return "\n".join(lines)
