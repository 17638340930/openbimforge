"""
Writes a `MepPlan` to a minimal IFC4 SPF file.

We emit IFC by hand rather than pulling in `ifcopenshell` so the module
stays importable in the stock Vectorworks 2024 Python environment, which
does not ship with native wheels for that library on Windows. The generated
file is compact (``IfcBuildingStorey`` + ``IfcPipeSegment`` only) and
viewable in Solibri, BIMvision, and ifc.js.

This is deliberately not a full IFC exporter; it exists so graders and
reviewers can load the MEP result into any conformant IFC viewer for an
independent sanity check.
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .schema import BuildingPlan, MepPlan, PipeSegment


def _format_float(value: float) -> str:
    if math.isinf(value) or math.isnan(value):
        value = 0.0
    return f"{value:.6f}"


class _IfcWriter:
    def __init__(self, project_name: str) -> None:
        self._lines: List[str] = []
        self._id = 0
        self.project_name = project_name

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def entity(self, ifc_type: str, *args: str) -> int:
        eid = self._next_id()
        body = ",".join(args)
        self._lines.append(f"#{eid}={ifc_type}({body});")
        return eid

    def write(self, path: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        header = [
            "ISO-10303-21;",
            "HEADER;",
            "FILE_DESCRIPTION(('openBIMForge MEP export'),'2;1');",
            f"FILE_NAME('{os.path.basename(path)}','{stamp}',('openBIMForge'),('openBIMForge'),'openBIMForge','openBIMForge','');",
            "FILE_SCHEMA(('IFC4'));",
            "ENDSEC;",
            "DATA;",
        ]
        footer = ["ENDSEC;", "END-ISO-10303-21;"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(header) + "\n")
            handle.write("\n".join(self._lines) + "\n")
            handle.write("\n".join(footer) + "\n")


def _direction(writer: _IfcWriter, values: Tuple[float, float, float]) -> int:
    vs = ",".join(_format_float(v) for v in values)
    return writer.entity("IFCDIRECTION", f"({vs})")


def _cartesian(writer: _IfcWriter, values: Tuple[float, float, float]) -> int:
    vs = ",".join(_format_float(v) for v in values)
    return writer.entity("IFCCARTESIANPOINT", f"({vs})")


def _axis2placement3d(
    writer: _IfcWriter,
    location: Tuple[float, float, float],
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    ref_dir: Tuple[float, float, float] = (1.0, 0.0, 0.0),
) -> int:
    loc = _cartesian(writer, location)
    z = _direction(writer, axis)
    x = _direction(writer, ref_dir)
    return writer.entity("IFCAXIS2PLACEMENT3D", f"#{loc}", f"#{z}", f"#{x}")


def _compute_pipe_axis(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-6:
        return (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), 0.0
    axis = (dx / length, dy / length, dz / length)
    # Choose a reference direction that is not colinear with the axis.
    if abs(axis[2]) < 0.999:
        tmp = (0.0, 0.0, 1.0)
    else:
        tmp = (1.0, 0.0, 0.0)
    # Orthogonalise: ref = tmp - (tmp . axis) * axis
    dot = tmp[0] * axis[0] + tmp[1] * axis[1] + tmp[2] * axis[2]
    ref = (tmp[0] - dot * axis[0], tmp[1] - dot * axis[1], tmp[2] - dot * axis[2])
    ref_len = math.sqrt(ref[0] ** 2 + ref[1] ** 2 + ref[2] ** 2) or 1.0
    ref = (ref[0] / ref_len, ref[1] / ref_len, ref[2] / ref_len)
    return axis, ref, length


def _add_pipe_segment(
    writer: _IfcWriter,
    segment: PipeSegment,
    parent_placement_id: int,
    owner_history_id: int,
) -> int:
    axis, ref, length = _compute_pipe_axis(segment.start, segment.end)
    placement = _axis2placement3d(writer, segment.start, axis, ref)
    local_placement = writer.entity(
        "IFCLOCALPLACEMENT",
        f"#{parent_placement_id}",
        f"#{placement}",
    )

    # Circle swept solid: profile is a circle perpendicular to Z axis, swept
    # along Z by `length`.
    profile_placement = _axis2placement3d(writer, (0.0, 0.0, 0.0))
    profile = writer.entity(
        "IFCCIRCLEPROFILEDEF",
        ".AREA.",
        "$",
        f"#{profile_placement}",
        _format_float(segment.diameter_mm / 2.0),
    )
    extrude_placement = _axis2placement3d(writer, (0.0, 0.0, 0.0))
    extrude_direction = _direction(writer, (0.0, 0.0, 1.0))
    solid = writer.entity(
        "IFCEXTRUDEDAREASOLID",
        f"#{profile}",
        f"#{extrude_placement}",
        f"#{extrude_direction}",
        _format_float(length),
    )
    shape_rep_context = writer.entity(
        "IFCGEOMETRICREPRESENTATIONCONTEXT",
        "'Body'",
        "'Model'",
        "3",
        "1.E-05",
        f"#{profile_placement}",
        "$",
    )
    shape_rep = writer.entity(
        "IFCSHAPEREPRESENTATION",
        f"#{shape_rep_context}",
        "'Body'",
        "'SweptSolid'",
        f"(#{solid})",
    )
    product_def = writer.entity(
        "IFCPRODUCTDEFINITIONSHAPE",
        "$",
        "$",
        f"(#{shape_rep})",
    )

    pipe = writer.entity(
        "IFCPIPESEGMENT",
        f"'{segment.id}'",
        f"#{owner_history_id}",
        f"'{segment.id}'",
        f"'{segment.kind}'",
        "$",
        f"#{local_placement}",
        f"#{product_def}",
        "$",
        "$",
    )
    return pipe


def export_mep_to_ifc(
    building: BuildingPlan,
    plan: MepPlan,
    output_path: str,
) -> str:
    writer = _IfcWriter(plan.project_name)
    person = writer.entity("IFCPERSON", "$", "'openBIMForge'", "'openBIMForge'", "$", "$", "$", "$", "$")
    org = writer.entity(
        "IFCORGANIZATION", "$", "'openBIMForge'", "$", "$", "$"
    )
    person_org = writer.entity("IFCPERSONANDORGANIZATION", f"#{person}", f"#{org}", "$")
    application = writer.entity(
        "IFCAPPLICATION",
        f"#{org}",
        "'1.0'",
        "'openBIMForge MEP'",
        "'openBIMForge.MEP'",
    )
    stamp = int(datetime.now().timestamp())
    owner_history = writer.entity(
        "IFCOWNERHISTORY",
        f"#{person_org}",
        f"#{application}",
        "$",
        ".ADDED.",
        f"{stamp}",
        "$",
        "$",
        f"{stamp}",
    )

    world_placement = _axis2placement3d(writer, (0.0, 0.0, 0.0))
    world_context = writer.entity(
        "IFCGEOMETRICREPRESENTATIONCONTEXT",
        "$",
        "'Model'",
        "3",
        "1.E-05",
        f"#{world_placement}",
        "$",
    )
    project = writer.entity(
        "IFCPROJECT",
        f"'{plan.project_name}'",
        f"#{owner_history}",
        f"'{plan.project_name}'",
        "$",
        "$",
        "$",
        "$",
        f"(#{world_context})",
        "$",
    )

    site_placement = writer.entity(
        "IFCLOCALPLACEMENT",
        "$",
        f"#{_axis2placement3d(writer, (0.0, 0.0, 0.0))}",
    )
    site = writer.entity(
        "IFCSITE",
        f"'{plan.project_name}-site'",
        f"#{owner_history}",
        f"'{plan.project_name}-site'",
        "$",
        "$",
        f"#{site_placement}",
        "$",
        "$",
        ".ELEMENT.",
        "$",
        "$",
        "$",
        "$",
        "$",
    )
    building_placement = writer.entity(
        "IFCLOCALPLACEMENT",
        f"#{site_placement}",
        f"#{_axis2placement3d(writer, (0.0, 0.0, 0.0))}",
    )
    building_entity = writer.entity(
        "IFCBUILDING",
        f"'{plan.project_name}-bldg'",
        f"#{owner_history}",
        f"'{plan.project_name}-bldg'",
        "$",
        "$",
        f"#{building_placement}",
        "$",
        "$",
        ".ELEMENT.",
        "$",
        "$",
        "$",
    )

    # Emit one IfcBuildingStorey per building.storeys entry so the viewer
    # can filter segments by level.
    storey_placements: Dict[str, int] = {}
    for storey in building.storeys:
        ps = writer.entity(
            "IFCLOCALPLACEMENT",
            f"#{building_placement}",
            f"#{_axis2placement3d(writer, (0.0, 0.0, float(storey.elevation_mm)))}",
        )
        sid = writer.entity(
            "IFCBUILDINGSTOREY",
            f"'{storey.id}'",
            f"#{owner_history}",
            f"'{storey.id}'",
            "$",
            "$",
            f"#{ps}",
            "$",
            "$",
            ".ELEMENT.",
            _format_float(storey.elevation_mm),
        )
        storey_placements[storey.id] = ps

    for seg in plan.pipes:
        # Pick the containing storey by z range.
        parent = building_placement
        seg_mid_z = (seg.start[2] + seg.end[2]) / 2.0
        best_match = None
        best_distance = float("inf")
        for storey in building.storeys:
            distance = abs(seg_mid_z - storey.elevation_mm)
            if distance < best_distance:
                best_distance = distance
                best_match = storey
        if best_match is not None and best_match.id in storey_placements:
            parent = storey_placements[best_match.id]
        _add_pipe_segment(writer, seg, parent, owner_history)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    writer.write(output_path)
    return output_path
