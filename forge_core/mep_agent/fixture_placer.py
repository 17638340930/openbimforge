"""
Stage B — Fixture placement.

Given a `BuildingPlan` with rooms of known type (bathroom, kitchen, ...), this
module decides the concrete `(x, y)` position of every sanitary fixture
inside each room. The placement is *rule-based* by default so the module has
no runtime LLM dependency and remains deterministic for unit tests. A later
iteration can swap in an LLM-assisted planner for tricky rooms without
touching the downstream stages.

Rules:

1. Toilet / squat toilet: against the longest wall of the room, 200 mm from
   that wall, anchored to the wall end that is furthest from the door.
2. Wash basin: against the wall adjacent to the door (to keep users moving
   forward when entering), 50 mm from the wall.
3. Urinal: uniformly distributed along the longest wall, 50 mm from it.
4. Floor drain: at the geometric lowest point of the room; if unknown, use
   the centroid.
5. Kitchen sink: against the longest wall.

Each fixture exposes a `connection_point` that sits 200 mm inward from the
fixture centre along its drain direction. This is the point the pipe router
will connect to.
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Tuple

from .schema import (
    BuildingPlan,
    Fixture,
    Point2D,
    Polygon,
    Room,
)


_KNOWLEDGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge",
)
_FIXTURE_FILE = os.path.join(_KNOWLEDGE_ROOT, "mep_fixtures.json")

_FIXTURE_CACHE: Dict[str, Dict] = {}


def _load_fixture_catalog() -> Dict[str, Dict]:
    if _FIXTURE_CACHE:
        return _FIXTURE_CACHE
    with open(_FIXTURE_FILE, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    _FIXTURE_CACHE.update(data)
    return _FIXTURE_CACHE


def _resolve_fixture_spec(fixture_type: str) -> Dict:
    catalog = _load_fixture_catalog()
    fixtures = catalog.get("fixtures", {})
    if fixture_type not in fixtures:
        raise KeyError(f"Unknown MEP fixture type: {fixture_type}")
    return fixtures[fixture_type]


def _room_template(room_type: str) -> List[Dict]:
    catalog = _load_fixture_catalog()
    templates = catalog.get("room_fixture_templates", {})
    return templates.get(room_type, [])


def _polygon_edges(polygon: Polygon) -> List[Tuple[Point2D, Point2D]]:
    n = len(polygon)
    return [(polygon[i], polygon[(i + 1) % n]) for i in range(n)]


def _edge_length(edge: Tuple[Point2D, Point2D]) -> float:
    (x1, y1), (x2, y2) = edge
    return math.hypot(x2 - x1, y2 - y1)


def _edge_normal_inward(edge: Tuple[Point2D, Point2D], centroid: Point2D) -> Tuple[float, float]:
    """Returns the unit inward normal of `edge` pointing toward `centroid`."""
    (x1, y1), (x2, y2) = edge
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length  # rotate 90° counter-clockwise
    mid = ((x1 + x2) / 2, (y1 + y2) / 2)
    toward = (centroid[0] - mid[0], centroid[1] - mid[1])
    if nx * toward[0] + ny * toward[1] < 0:
        nx, ny = -nx, -ny
    return nx, ny


def _longest_edge(polygon: Polygon) -> Tuple[Point2D, Point2D]:
    edges = _polygon_edges(polygon)
    return max(edges, key=_edge_length)


def _edge_nearest_to_point(polygon: Polygon, point: Point2D) -> Tuple[Point2D, Point2D]:
    edges = _polygon_edges(polygon)
    best = edges[0]
    best_dist = float("inf")
    for edge in edges:
        (x1, y1), (x2, y2) = edge
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dist = math.hypot(mx - point[0], my - point[1])
        if dist < best_dist:
            best_dist = dist
            best = edge
    return best


def _edge_farthest_from_point(polygon: Polygon, point: Point2D) -> Tuple[Point2D, Point2D]:
    edges = _polygon_edges(polygon)
    best = edges[0]
    best_dist = -1.0
    for edge in edges:
        (x1, y1), (x2, y2) = edge
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dist = math.hypot(mx - point[0], my - point[1])
        if dist > best_dist:
            best_dist = dist
            best = edge
    return best


def _place_along_edge(
    edge: Tuple[Point2D, Point2D],
    fraction: float,
    inward_offset: float,
    centroid: Point2D,
) -> Tuple[Point2D, float]:
    """Returns a point placed ``inward_offset`` mm away from ``edge``.

    ``fraction`` is where along the edge the anchor sits (0 = start, 1 = end).
    The returned rotation (degrees) points the fixture front toward the room
    interior.
    """
    (x1, y1), (x2, y2) = edge
    anchor = (x1 + (x2 - x1) * fraction, y1 + (y2 - y1) * fraction)
    nx, ny = _edge_normal_inward(edge, centroid)
    pos = (anchor[0] + nx * inward_offset, anchor[1] + ny * inward_offset)
    rotation_deg = math.degrees(math.atan2(ny, nx))
    return pos, rotation_deg


def _door_or_longest_midpoint(room: Room) -> Point2D:
    if room.door is not None:
        return room.door
    edge = _longest_edge(room.polygon)
    return ((edge[0][0] + edge[1][0]) / 2.0, (edge[0][1] + edge[1][1]) / 2.0)


def _place_single_fixture(
    room: Room,
    fixture_type: str,
    index: int,
    total_of_type: int,
) -> Tuple[Point2D, float, Point2D]:
    """Core placement heuristic. Returns (position, rotation, connection)."""
    spec = _resolve_fixture_spec(fixture_type)
    centroid = room.centroid()
    door_point = _door_or_longest_midpoint(room)

    # Default: longest wall, fraction based on index.
    target_edge = _longest_edge(room.polygon)
    inward = 50.0 + max(spec["footprint_mm"]) / 2.0

    if fixture_type in {"toilet", "squat_toilet"}:
        target_edge = _edge_farthest_from_point(room.polygon, door_point)
        inward = 50.0 + max(spec["footprint_mm"]) / 2.0
    elif fixture_type == "urinal":
        target_edge = _longest_edge(room.polygon)
        inward = 50.0 + max(spec["footprint_mm"]) / 2.0
    elif fixture_type == "wash_basin":
        target_edge = _edge_nearest_to_point(room.polygon, door_point)
        inward = 50.0 + max(spec["footprint_mm"]) / 2.0
    elif fixture_type == "kitchen_sink":
        target_edge = _longest_edge(room.polygon)
        inward = 50.0 + max(spec["footprint_mm"]) / 2.0
    elif fixture_type == "floor_drain":
        pos = centroid
        return pos, 0.0, pos
    elif fixture_type == "shower":
        target_edge = _longest_edge(room.polygon)
        inward = 50.0 + max(spec["footprint_mm"]) / 2.0

    # Distribute multiple same-type fixtures along the chosen edge.
    if total_of_type <= 1:
        fraction = 0.5
    else:
        fraction = 0.15 + 0.7 * index / max(1, total_of_type - 1)

    position, rotation = _place_along_edge(target_edge, fraction, inward, centroid)

    # Connection point is pushed slightly inward so the pipe router has
    # clearance from the wall.
    nx, ny = _edge_normal_inward(target_edge, centroid)
    connection = (position[0] + nx * 120.0, position[1] + ny * 120.0)
    return position, rotation, connection


def place_fixtures(
    building: BuildingPlan,
    storey_slab_thickness_mm: float = 150.0,
) -> List[Fixture]:
    """Produces a deterministic fixture layout for every plumbing-active room.

    The returned list is ordered by storey then by room then by fixture
    template index, so deterministic tests can compare serialised output.
    """
    fixtures: List[Fixture] = []
    counter = 0
    for storey in building.storeys:
        for room in storey.rooms:
            template = _room_template(room.type)
            if not template:
                continue

            # Expand the template "N copies of type X" into a flat list first
            # so same-type fixtures can be distributed along their wall.
            expanded: List[str] = []
            for entry in template:
                expanded.extend([entry["type"]] * int(entry.get("count", 1)))

            per_type_total = {
                ftype: expanded.count(ftype) for ftype in set(expanded)
            }
            per_type_index: Dict[str, int] = {ftype: 0 for ftype in per_type_total}

            for fixture_type in expanded:
                spec = _resolve_fixture_spec(fixture_type)
                idx = per_type_index[fixture_type]
                per_type_index[fixture_type] += 1

                position, rotation, connection = _place_single_fixture(
                    room,
                    fixture_type,
                    idx,
                    per_type_total[fixture_type],
                )

                # Drain outlet elevation sits at the storey slab top minus a
                # small allowance so downstream pipe routing has ceiling void.
                outlet_z = storey.elevation_mm - storey_slab_thickness_mm

                fixtures.append(
                    Fixture(
                        id=f"fx_{counter:04d}_{fixture_type}",
                        type=fixture_type,
                        room_id=room.id,
                        storey_id=storey.id,
                        position=position,
                        rotation_deg=rotation,
                        connection_point=connection,
                        discharge_unit=float(spec.get("discharge_unit", 0.0)),
                        drain_diameter_mm=float(spec.get("drain_diameter_mm", 50)),
                        elevation_mm=outlet_z,
                    )
                )
                counter += 1

    return fixtures
