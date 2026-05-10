"""
Stage D — Horizontal pipe routing.

Implements a constrained A* search that routes a branch pipe from each
fixture's connection point to its assigned stack inside the ceiling void of
its storey.

The routing space is a uniform XY grid per storey. Each cell has four
neighbours (Manhattan movement), because plumbing practice favours
right-angle turns over diagonal runs for maintenance. Turn penalties
further discourage unnecessary bends.

Obstacles supported:

- Storey outline (pipes cannot leave the building).
- Room polygons (pipes run in corridors / ceiling void above corridors,
  *not* through room interiors). This is a deliberately conservative rule
  that produces visually plausible routes; a production-grade system would
  also avoid crossing beams, but that requires structural data we don't
  have yet.

After the 2D path is solved, slope is applied post-hoc: the connection
point at the fixture is the *high* end and the stack is the *low* end, with
the elevation decreasing linearly by ``slope_pct`` of the total planar
length. The drop is constrained to fit inside the ceiling void.
"""

from __future__ import annotations

import heapq
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .schema import (
    BuildingPlan,
    Fixture,
    Obstacle,
    PipeSegment,
    Point2D,
    Polygon,
    Stack,
    Storey,
    point_in_polygon,
    segment_length,
)


Cell = Tuple[int, int]


# --- Grid construction ------------------------------------------------------


def _polygon_bbox(polygon: Polygon) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _build_walkable_mask(
    storey: Storey,
    cell_size_mm: float,
    obstacle_inflate_mm: float,
) -> Tuple[List[List[bool]], float, float, int, int]:
    """Returns a 2D mask of walkable cells and the grid origin.

    A cell is walkable when its centre sits inside the storey outline
    **and** outside every inflated obstacle polygon. Room polygons are
    intentionally *not* treated as obstacles because plumbing branch
    pipes run in the ceiling void above the floor slab, which is a free
    plenum spanning every room. Beams and columns are the real
    obstacles, and are modelled as ``Storey.obstacles``.

    ``obstacle_inflate_mm`` pushes the obstacle polygons outward so the
    pipe keeps clearance to the beam/column edges (default 100 mm,
    roughly the insulation + mounting clearance used in practice).
    """
    minx, miny, maxx, maxy = _polygon_bbox(storey.outline)
    width_cells = max(1, int(math.ceil((maxx - minx) / cell_size_mm)))
    height_cells = max(1, int(math.ceil((maxy - miny) / cell_size_mm)))
    origin_x = minx
    origin_y = miny

    inflated_obstacles: List[Polygon] = [
        _inflate_polygon(obstacle.polygon, obstacle_inflate_mm)
        for obstacle in storey.obstacles
    ]

    mask: List[List[bool]] = []
    for gy in range(height_cells):
        row: List[bool] = []
        for gx in range(width_cells):
            cx = origin_x + (gx + 0.5) * cell_size_mm
            cy = origin_y + (gy + 0.5) * cell_size_mm
            walkable = point_in_polygon((cx, cy), storey.outline)
            if walkable:
                for poly in inflated_obstacles:
                    if point_in_polygon((cx, cy), poly):
                        walkable = False
                        break
            row.append(walkable)
        mask.append(row)
    return mask, origin_x, origin_y, width_cells, height_cells


def _inflate_polygon(polygon: Polygon, amount_mm: float) -> Polygon:
    """Naive polygon inflation around its centroid.

    Good enough for axis-aligned room polygons that the Architect typically
    emits; not correct for general concave shapes, but those are rare in
    the building shell produced by the upstream pipeline.
    """
    if amount_mm <= 0:
        return list(polygon)
    cx = sum(p[0] for p in polygon) / len(polygon)
    cy = sum(p[1] for p in polygon) / len(polygon)
    inflated: Polygon = []
    for x, y in polygon:
        dx, dy = x - cx, y - cy
        length = math.hypot(dx, dy) or 1.0
        scale = (length + amount_mm) / length
        inflated.append((cx + dx * scale, cy + dy * scale))
    return inflated


def _point_to_cell(
    point: Point2D,
    origin_x: float,
    origin_y: float,
    cell_size_mm: float,
    width: int,
    height: int,
) -> Cell:
    gx = int((point[0] - origin_x) / cell_size_mm)
    gy = int((point[1] - origin_y) / cell_size_mm)
    gx = max(0, min(width - 1, gx))
    gy = max(0, min(height - 1, gy))
    return gx, gy


def _cell_to_point(
    cell: Cell,
    origin_x: float,
    origin_y: float,
    cell_size_mm: float,
) -> Point2D:
    gx, gy = cell
    return origin_x + (gx + 0.5) * cell_size_mm, origin_y + (gy + 0.5) * cell_size_mm


def _nearest_walkable(
    mask: List[List[bool]],
    cell: Cell,
    max_radius: int = 30,
) -> Optional[Cell]:
    """Returns the nearest walkable cell to ``cell`` (including itself).

    Used when a requested start/goal point sits inside a room polygon. The
    router still needs to anchor the route at the fixture's connection
    point; we relax that single cell onto the closest walkable neighbour so
    the pipe exits the room at the nearest wall.
    """
    width = len(mask[0]) if mask else 0
    height = len(mask)
    if not (0 <= cell[0] < width and 0 <= cell[1] < height):
        return None
    for radius in range(max_radius + 1):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                gx, gy = cell[0] + dx, cell[1] + dy
                if 0 <= gx < width and 0 <= gy < height and mask[gy][gx]:
                    return gx, gy
    return None


def _punch_cell(mask: List[List[bool]], cell: Cell) -> List[List[bool]]:
    """Returns a copy of ``mask`` with a single cell forced walkable.

    Callers use this to guarantee that the A* source/target nodes are
    traversable regardless of the room inflation pass. The copy is cheap
    because Python's list layout is shallow and we only toggle one bit.
    """
    if not (0 <= cell[1] < len(mask) and 0 <= cell[0] < len(mask[0])):
        return mask
    patched = [row[:] for row in mask]
    patched[cell[1]][cell[0]] = True
    return patched


# --- A* core ----------------------------------------------------------------


def _heuristic(a: Cell, b: Cell) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _neighbours(cell: Cell, width: int, height: int) -> Iterable[Tuple[Cell, Tuple[int, int]]]:
    gx, gy = cell
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = gx + dx, gy + dy
        if 0 <= nx < width and 0 <= ny < height:
            yield (nx, ny), (dx, dy)


def _a_star(
    start: Cell,
    goal: Cell,
    mask: List[List[bool]],
    turn_penalty: float = 2.0,
) -> Optional[List[Cell]]:
    width = len(mask[0])
    height = len(mask)
    if not mask[start[1]][start[0]] or not mask[goal[1]][goal[0]]:
        return None

    open_heap: List[Tuple[float, int, Cell, Optional[Tuple[int, int]]]] = []
    counter = 0
    heapq.heappush(open_heap, (0.0, counter, start, None))
    came_from: Dict[Cell, Tuple[Cell, Tuple[int, int]]] = {}
    g_score: Dict[Cell, float] = {start: 0.0}

    while open_heap:
        _, _, current, last_dir = heapq.heappop(open_heap)
        if current == goal:
            # Reconstruct.
            path: List[Cell] = [current]
            node = current
            while node in came_from:
                node, _ = came_from[node]
                path.append(node)
            return list(reversed(path))

        for neighbour, direction in _neighbours(current, width, height):
            if not mask[neighbour[1]][neighbour[0]]:
                continue
            step_cost = 1.0
            if last_dir is not None and direction != last_dir:
                step_cost += turn_penalty
            tentative = g_score[current] + step_cost
            if tentative < g_score.get(neighbour, float("inf")):
                came_from[neighbour] = (current, direction)
                g_score[neighbour] = tentative
                priority = tentative + _heuristic(neighbour, goal)
                counter += 1
                heapq.heappush(open_heap, (priority, counter, neighbour, direction))

    return None


def _compress_collinear(path: List[Cell]) -> List[Cell]:
    if len(path) <= 2:
        return path[:]
    compressed = [path[0]]
    for i in range(1, len(path) - 1):
        prev, cur, nxt = path[i - 1], path[i], path[i + 1]
        dx1, dy1 = cur[0] - prev[0], cur[1] - prev[1]
        dx2, dy2 = nxt[0] - cur[0], nxt[1] - cur[1]
        if (dx1, dy1) != (dx2, dy2):
            compressed.append(cur)
    compressed.append(path[-1])
    return compressed


# --- Public API ------------------------------------------------------------


def route_branches(
    building: BuildingPlan,
    fixtures: List[Fixture],
    stacks: List[Stack],
    cell_size_mm: float = 200.0,
    obstacle_clearance_mm: float = 100.0,
    min_slope_pct: float = 2.0,
) -> Tuple[List[PipeSegment], List[str]]:
    """Routes branch pipes from every fixture to its stack via merge trees.

    For every stack we build a merge tree (see ``merge_tree.py``): all
    fixtures attached to the stack become leaves, the stack is the root,
    and Prim's algorithm determines a right-angle preferring merge
    topology. Each tree edge is then materialised by an A* path in the
    ceiling void.

    The returned segments carry:
    - ``fixture_ids`` populated with the **downstream** fixtures for
      cumulative-DU sizing (Stage E).
    - ``stack_id`` set to the parent stack.
    - ``kind == "branch"`` for leaf→merge segments and
      ``kind == "trunk"`` for merge→root (merged) segments; the sizing
      stage treats them differently.

    Returns the list of segments plus human-readable warnings for any
    fixture that could not be materialised (mostly for diagnostic use).
    """
    from .merge_tree import annotate_cumulative_du, build_merge_tree

    if not fixtures or not stacks:
        return [], []

    fixtures_by_id: Dict[str, Fixture] = {fx.id: fx for fx in fixtures}
    storey_by_id = {s.id: s for s in building.storeys}
    grid_cache: Dict[str, Tuple[List[List[bool]], float, float, int, int]] = {}
    warnings: List[str] = []
    pipes: List[PipeSegment] = []
    segment_counter = 0

    for stack in stacks:
        tree = build_merge_tree(stack, fixtures_by_id)
        annotate_cumulative_du(tree, fixtures_by_id)

        storey_id = tree.storey_id
        storey = storey_by_id.get(storey_id)
        if storey is None:
            warnings.append(
                f"merge tree for stack {stack.id} references unknown storey {storey_id}"
            )
            continue
        if storey_id not in grid_cache:
            grid_cache[storey_id] = _build_walkable_mask(
                storey, cell_size_mm, obstacle_clearance_mm
            )
        mask, ox, oy, width, height = grid_cache[storey_id]

        # Every tree edge is routed child -> parent. That direction also
        # matches the flow direction so the slope drop aligns with reality
        # (parent is downstream of child).
        for child, parent in tree.iter_edges():
            downstream_fixtures = _collect_downstream_fixtures(tree, child.id)
            raw_start = _point_to_cell(
                child.position, ox, oy, cell_size_mm, width, height
            )
            raw_goal = _point_to_cell(
                parent.position, ox, oy, cell_size_mm, width, height
            )
            start_cell = (
                raw_start if mask[raw_start[1]][raw_start[0]] else _nearest_walkable(mask, raw_start)
            )
            goal_cell = raw_goal
            search_mask = (
                mask if mask[raw_goal[1]][raw_goal[0]] else _punch_cell(mask, raw_goal)
            )
            if start_cell is None:
                warnings.append(
                    f"merge node {child.id} could not resolve walkable start"
                )
                continue
            path = _a_star(start_cell, goal_cell, search_mask)
            if not path:
                warnings.append(
                    f"merge edge {child.id}->{parent.id} has no A* path"
                )
                continue

            plan_points = [
                _cell_to_point(cell, ox, oy, cell_size_mm) for cell in _compress_collinear(path)
            ]
            if plan_points:
                plan_points[0] = child.position
                plan_points[-1] = parent.position
            if len(plan_points) < 2:
                plan_points = [child.position, parent.position]

            # Slope — carried by planar length, capped at the ceiling void.
            cumulative = [0.0]
            for i in range(1, len(plan_points)):
                cumulative.append(
                    cumulative[-1] + segment_length(plan_points[i - 1], plan_points[i])
                )
            total_len = cumulative[-1] or 1.0
            max_drop = building.ceiling_void_mm - 100.0
            desired_drop = total_len * (min_slope_pct / 100.0)
            drop = min(desired_drop, max_drop)
            actual_slope_pct = (drop / total_len) * 100.0 if total_len else min_slope_pct

            # Reference elevation is the downstream fixture's outlet (for
            # leaf edges) or the downstream-most fixture's outlet (for
            # trunks). This keeps all merged trunks below the fixtures
            # they serve without violating the ceiling void budget.
            ref_elevation = _downstream_reference_elevation(
                child, fixtures_by_id, downstream_fixtures
            )
            start_z = ref_elevation - 50.0
            kind = "branch" if child.fixture_id is not None else "trunk"

            for i in range(1, len(plan_points)):
                p0 = plan_points[i - 1]
                p1 = plan_points[i]
                z0 = start_z - drop * (cumulative[i - 1] / total_len)
                z1 = start_z - drop * (cumulative[i] / total_len)
                pipes.append(
                    PipeSegment(
                        id=f"seg_{segment_counter:05d}",
                        kind=kind,
                        start=(p0[0], p0[1], z0),
                        end=(p1[0], p1[1], z1),
                        # diameter is a placeholder; Stage E sizes by DU.
                        diameter_mm=0.0,
                        slope_pct=actual_slope_pct,
                        fixture_ids=list(downstream_fixtures),
                        stack_id=stack.id,
                    )
                )
                segment_counter += 1

    return pipes, warnings


def _collect_downstream_fixtures(tree, node_id: str) -> List[str]:
    """Returns every fixture id in the subtree rooted at ``node_id``."""
    collected: List[str] = []
    stack_to_visit = [node_id]
    while stack_to_visit:
        current_id = stack_to_visit.pop()
        node = tree.nodes[current_id]
        if node.fixture_id is not None:
            collected.append(node.fixture_id)
        stack_to_visit.extend(node.children)
    return collected


def _downstream_reference_elevation(
    node,
    fixtures_by_id: Dict[str, Fixture],
    downstream_fixture_ids: List[str],
) -> float:
    if node.fixture_id is not None:
        fixture = fixtures_by_id.get(node.fixture_id)
        if fixture is not None:
            return fixture.elevation_mm
    # Internal merge node: take the minimum outlet elevation of its
    # downstream fixtures so the trunk runs below all of them.
    elevations = [
        fixtures_by_id[fid].elevation_mm
        for fid in downstream_fixture_ids
        if fid in fixtures_by_id
    ]
    if elevations:
        return min(elevations)
    return 0.0


def build_stack_segments(
    building: BuildingPlan,
    stacks: Sequence[Stack],
) -> List[PipeSegment]:
    """Emits one vertical `PipeSegment` per stack covering the full height."""
    segments: List[PipeSegment] = []
    for idx, stack in enumerate(stacks):
        segments.append(
            PipeSegment(
                id=f"stk_seg_{idx:03d}",
                kind="stack",
                start=(stack.position[0], stack.position[1], stack.base_elevation_mm),
                end=(stack.position[0], stack.position[1], stack.top_elevation_mm - 300.0),
                diameter_mm=stack.diameter_mm or 100.0,
                slope_pct=0.0,
                stack_id=stack.id,
            )
        )
        # Vent stub above the roof.
        segments.append(
            PipeSegment(
                id=f"vent_seg_{idx:03d}",
                kind="vent",
                start=(stack.position[0], stack.position[1], stack.top_elevation_mm - 300.0),
                end=(stack.position[0], stack.position[1], stack.top_elevation_mm),
                diameter_mm=max(75.0, (stack.diameter_mm or 100.0) * 0.8),
                slope_pct=0.0,
                stack_id=stack.id,
            )
        )
    return segments
