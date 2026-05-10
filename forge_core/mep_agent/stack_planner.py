"""
Stage C — Vertical stack planning.

Clusters the XY positions of every plumbing fixture (projected onto the
ground plane, since stacks are vertical) and places a soil stack at each
cluster centre. When shafts are defined on a storey the stack centre snaps
to the nearest shaft centroid; otherwise the raw cluster centre is used.

The clustering is a lightweight K-means variant that picks ``k`` adaptively
based on a maximum-spread heuristic: start with one cluster, then split the
one with the worst spread until every cluster's spread is below
``max_stack_spacing_mm / 2``. This avoids pulling in a scikit-learn
dependency.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .schema import (
    BuildingPlan,
    Fixture,
    Point2D,
    Polygon,
    Shaft,
    Stack,
    polygon_centroid,
)


def _kmeans(
    points: List[Point2D],
    k: int,
    max_iter: int = 30,
) -> Tuple[List[Point2D], List[int]]:
    if not points:
        return [], []
    centroids = [points[i % len(points)] for i in range(k)]
    assignments = [0] * len(points)
    for _ in range(max_iter):
        # Assign.
        new_assign = []
        for point in points:
            best_idx = 0
            best_dist = float("inf")
            for j, centre in enumerate(centroids):
                dist = (point[0] - centre[0]) ** 2 + (point[1] - centre[1]) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best_idx = j
            new_assign.append(best_idx)
        if new_assign == assignments:
            break
        assignments = new_assign
        # Update.
        new_centroids: List[Point2D] = []
        for j in range(k):
            members = [pt for pt, a in zip(points, assignments) if a == j]
            if members:
                cx = sum(p[0] for p in members) / len(members)
                cy = sum(p[1] for p in members) / len(members)
                new_centroids.append((cx, cy))
            else:
                new_centroids.append(centroids[j])
        centroids = new_centroids
    return centroids, assignments


def _cluster_spread(points: List[Point2D], centre: Point2D) -> float:
    if not points:
        return 0.0
    return max(math.hypot(p[0] - centre[0], p[1] - centre[1]) for p in points)


def _adaptive_cluster(
    points: List[Point2D],
    max_cluster_radius_mm: float,
) -> Tuple[List[Point2D], List[int]]:
    if not points:
        return [], []
    for k in range(1, min(len(points), 12) + 1):
        centroids, assignments = _kmeans(points, k)
        ok = True
        for j, centre in enumerate(centroids):
            members = [pt for pt, a in zip(points, assignments) if a == j]
            if _cluster_spread(members, centre) > max_cluster_radius_mm:
                ok = False
                break
        if ok:
            return centroids, assignments
    return _kmeans(points, min(len(points), 12))


def _snap_to_shaft(centre: Point2D, shafts: List[Shaft]) -> Point2D:
    if not shafts:
        return centre
    best = centre
    best_dist = float("inf")
    for shaft in shafts:
        sc = polygon_centroid(shaft.polygon)
        dist = math.hypot(sc[0] - centre[0], sc[1] - centre[1])
        if dist < best_dist:
            best_dist = dist
            best = sc
    return best


def plan_stacks(
    building: BuildingPlan,
    fixtures: List[Fixture],
    max_cluster_radius_mm: float = 6000.0,
) -> List[Stack]:
    """Returns one stack per cluster of fixtures, aligned vertically across
    every storey that hosts at least one fixture from that cluster."""
    if not fixtures:
        return []

    # Use ground floor fixtures to seed clusters when available, otherwise
    # pool all fixtures.
    ground_storey = min(building.storeys, key=lambda s: s.elevation_mm)
    seed_fixtures = [f for f in fixtures if f.storey_id == ground_storey.id]
    if not seed_fixtures:
        seed_fixtures = fixtures

    points = [f.connection_point for f in seed_fixtures]
    centroids, _ = _adaptive_cluster(points, max_cluster_radius_mm)

    # Gather shafts from every storey (shafts repeat vertically).
    all_shafts = [shaft for storey in building.storeys for shaft in storey.shafts]
    aligned_centroids = [_snap_to_shaft(c, all_shafts) for c in centroids]

    # Now assign every fixture (not only the seed set) to the nearest cluster.
    assignments: Dict[str, int] = {}
    for fix in fixtures:
        best = 0
        best_dist = float("inf")
        for j, centre in enumerate(aligned_centroids):
            dist = math.hypot(
                fix.connection_point[0] - centre[0],
                fix.connection_point[1] - centre[1],
            )
            if dist < best_dist:
                best_dist = dist
                best = j
        assignments[fix.id] = best

    top_storey = max(building.storeys, key=lambda s: s.elevation_mm)
    base_storey = min(building.storeys, key=lambda s: s.elevation_mm)
    base_elev = base_storey.elevation_mm - (building.ceiling_void_mm + 500.0)
    top_elev = (
        (building.roof_elevation_mm if building.roof_elevation_mm is not None else
         top_storey.elevation_mm + top_storey.height_mm)
        + 300.0  # vent stub above roof
    )

    stacks: List[Stack] = []
    for j, centre in enumerate(aligned_centroids):
        member_ids = [fid for fid, cluster in assignments.items() if cluster == j]
        if not member_ids:
            continue
        cumulative_du = sum(f.discharge_unit for f in fixtures if f.id in member_ids)
        stacks.append(
            Stack(
                id=f"stk_{j:02d}",
                position=centre,
                from_storey=base_storey.id,
                to_storey=top_storey.id,
                base_elevation_mm=base_elev,
                top_elevation_mm=top_elev,
                diameter_mm=0.0,  # filled in by sizing stage
                fixture_ids=member_ids,
                cumulative_du=cumulative_du,
            )
        )
    return stacks
