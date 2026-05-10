"""
Data structures that flow between MEP pipeline stages.

All units are millimetres unless noted otherwise. Coordinates are `(x, y)` in
the building's own frame, with ``z`` being the storey elevation (relative to
the ground floor).

The dataclasses are intentionally `@dataclass` with plain types so the whole
plan can be serialised to JSON by `asdict()` with no custom encoder.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


Point2D = Tuple[float, float]
Polygon = List[Point2D]


# --- Building context -------------------------------------------------------


@dataclass
class Room:
    id: str
    storey_id: str
    type: str  # e.g. "bathroom", "kitchen", "tea_room"
    polygon: Polygon
    door: Optional[Point2D] = None  # door centre in room frame
    label_zh: Optional[str] = None

    def bbox(self) -> Tuple[float, float, float, float]:
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)

    def centroid(self) -> Point2D:
        minx, miny, maxx, maxy = self.bbox()
        return (minx + maxx) / 2.0, (miny + maxy) / 2.0


@dataclass
class Shaft:
    id: str
    polygon: Polygon
    label_zh: Optional[str] = None


@dataclass
class Obstacle:
    """A physical obstacle the MEP router must avoid in the ceiling void.

    Structural beams and primary columns are the canonical use case. The
    obstacle is expressed as a planar polygon (projected onto the storey
    floor) plus an optional Z range. When the Z range is omitted the
    obstacle is assumed to span the entire ceiling void and therefore
    always blocks routing.
    """

    id: str
    polygon: Polygon
    kind: str = "beam"  # "beam" | "column" | "equipment"
    z_min_mm: Optional[float] = None
    z_max_mm: Optional[float] = None
    label_zh: Optional[str] = None


@dataclass
class Storey:
    id: str
    index: int
    elevation_mm: float
    height_mm: float
    outline: Polygon
    rooms: List[Room] = field(default_factory=list)
    shafts: List[Shaft] = field(default_factory=list)
    obstacles: List[Obstacle] = field(default_factory=list)


@dataclass
class BuildingPlan:
    """Input for the MEP pipeline.

    Produced either by the Nexus Architect pipeline (via
    `forge_core.mep_agent.bridge`) or manually authored for tests / demos.
    """

    project_name: str
    storeys: List[Storey]
    ceiling_void_mm: float = 500.0
    ground_elevation_mm: float = 0.0
    roof_elevation_mm: Optional[float] = None

    def serialise(self) -> Dict[str, Any]:
        return asdict(self)


# --- MEP results ------------------------------------------------------------


@dataclass
class Fixture:
    id: str
    type: str
    room_id: str
    storey_id: str
    position: Point2D
    rotation_deg: float
    connection_point: Point2D  # where the drain pipe starts
    discharge_unit: float
    drain_diameter_mm: float
    elevation_mm: float  # z of the drain outlet (storey slab top minus slab thickness)


@dataclass
class Stack:
    id: str
    position: Point2D
    from_storey: str
    to_storey: str
    base_elevation_mm: float
    top_elevation_mm: float
    diameter_mm: float
    fixture_ids: List[str] = field(default_factory=list)
    cumulative_du: float = 0.0


@dataclass
class PipeSegment:
    id: str
    kind: str  # "branch" | "stack" | "vent" | "drop" | "cleanout"
    start: Tuple[float, float, float]
    end: Tuple[float, float, float]
    diameter_mm: float
    slope_pct: float = 0.0
    material: str = "PVC"
    fixture_ids: List[str] = field(default_factory=list)
    stack_id: Optional[str] = None


@dataclass
class MepPlan:
    project_name: str
    fixtures: List[Fixture] = field(default_factory=list)
    stacks: List[Stack] = field(default_factory=list)
    pipes: List[PipeSegment] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def serialise(self) -> Dict[str, Any]:
        return asdict(self)


# --- Helpers ---------------------------------------------------------------


def point_in_polygon(point: Point2D, polygon: Polygon) -> bool:
    """Ray casting point-in-polygon test.

    Accepts degenerate polygons (returns False) and supports convex /
    concave shapes.
    """
    x, y = point
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def polygon_centroid(polygon: Polygon) -> Point2D:
    """Centroid of a simple polygon; falls back to bbox centre when degenerate."""
    n = len(polygon)
    if n < 3:
        xs = [p[0] for p in polygon] or [0.0]
        ys = [p[1] for p in polygon] or [0.0]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cx = cy = area = 0.0
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
        area += cross
    area *= 0.5
    if abs(area) < 1e-6:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return cx / (6 * area), cy / (6 * area)


def segment_length(a: Point2D, b: Point2D) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def segment_length_3d(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return (
        (a[0] - b[0]) ** 2
        + (a[1] - b[1]) ** 2
        + (a[2] - b[2]) ** 2
    ) ** 0.5
