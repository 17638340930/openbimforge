"""
Stage D.5 — Merge tree synthesis.

Classical BIM drainage layouts do not connect every fixture to the stack
with an independent branch. Real installations **merge** two to three
fixtures onto a shared horizontal run, then connect the merged run to the
stack. This module produces that structure as a tree:

- leaf nodes = fixture connection points
- internal nodes = Y-fitting merge points inferred from the MST
- root = stack position

The tree is built by running Prim's algorithm on the complete graph of
{stack} ∪ {fixture connection points}, using Manhattan distance as the
edge weight (right-angle branches are cheap because walls are
axis-aligned). Internal merge points are then inserted wherever two or
more tree edges meet; this is what allows cumulative discharge-unit
sizing to take effect downstream.

The function intentionally returns a plain Python tree rather than
calling the A* router itself; the next stage (``pipe_router``) walks the
tree and uses the grid-based A* to materialise every tree edge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .schema import Fixture, Point2D, Stack


@dataclass
class MergeNode:
    """One node in the drainage merge tree.

    ``fixture_id`` is set on leaf nodes that correspond to a physical
    fixture outlet. Internal merge nodes (Y-fittings) and the root (the
    stack) leave it as ``None``.
    """

    id: str
    position: Point2D
    storey_id: str
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    fixture_id: Optional[str] = None
    is_stack_root: bool = False
    # Populated by the downstream cumulative-DU pass.
    cumulative_du: float = 0.0


@dataclass
class MergeTree:
    stack_id: str
    storey_id: str
    nodes: Dict[str, MergeNode] = field(default_factory=dict)
    root_id: str = ""

    def iter_edges(self) -> List[Tuple[MergeNode, MergeNode]]:
        """Iterates every (child, parent) edge in the tree."""
        edges: List[Tuple[MergeNode, MergeNode]] = []
        for node in self.nodes.values():
            if node.parent and node.parent in self.nodes:
                edges.append((node, self.nodes[node.parent]))
        return edges


def _manhattan(a: Point2D, b: Point2D) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _prim_mst(
    points: List[Point2D],
    root_index: int,
) -> List[Tuple[int, int]]:
    """Returns Prim's MST as a list of (parent_idx, child_idx) edges.

    The graph is the complete graph over ``points`` with Manhattan
    distance as the edge weight. ``root_index`` is added to the tree
    first, so the resulting edges form a rooted tree centred on the stack.
    """
    n = len(points)
    if n <= 1:
        return []
    in_tree = [False] * n
    in_tree[root_index] = True
    best_parent: List[Optional[int]] = [None] * n
    best_cost = [math.inf] * n
    best_cost[root_index] = 0.0
    edges: List[Tuple[int, int]] = []

    for neighbour in range(n):
        if neighbour == root_index:
            continue
        best_cost[neighbour] = _manhattan(points[root_index], points[neighbour])
        best_parent[neighbour] = root_index

    for _ in range(n - 1):
        cheapest = -1
        cheapest_cost = math.inf
        for idx in range(n):
            if in_tree[idx]:
                continue
            if best_cost[idx] < cheapest_cost:
                cheapest_cost = best_cost[idx]
                cheapest = idx
        if cheapest == -1:
            break
        parent = best_parent[cheapest]
        if parent is None:
            break
        edges.append((parent, cheapest))
        in_tree[cheapest] = True
        # Relax the remaining frontier against the newly added node.
        for other in range(n):
            if in_tree[other]:
                continue
            dist = _manhattan(points[cheapest], points[other])
            if dist < best_cost[other]:
                best_cost[other] = dist
                best_parent[other] = cheapest
    return edges


def build_merge_tree(
    stack: Stack,
    fixtures_by_id: Dict[str, Fixture],
) -> MergeTree:
    """Builds a rooted merge tree for one stack.

    The tree's root is the stack position; every fixture assigned to the
    stack becomes a leaf. Edge weights are Manhattan distances so that
    the resulting tree prefers right-angle routes that align with the
    eventual A* grid.

    The returned tree is *not yet annotated* with cumulative discharge
    units. Call `annotate_cumulative_du` once the tree is finalised so
    the sizing stage can pick diameters for each tree edge.
    """
    members = [fixtures_by_id[fid] for fid in stack.fixture_ids if fid in fixtures_by_id]
    storey_id = members[0].storey_id if members else stack.from_storey

    # Build the point list with the stack at index 0 so MST rooting is trivial.
    points: List[Point2D] = [stack.position]
    labels: List[Tuple[str, Optional[str]]] = [(f"root_{stack.id}", None)]
    for fx in members:
        points.append(fx.connection_point)
        labels.append((f"leaf_{fx.id}", fx.id))

    tree = MergeTree(stack_id=stack.id, storey_id=storey_id, root_id=labels[0][0])
    tree.nodes[labels[0][0]] = MergeNode(
        id=labels[0][0],
        position=points[0],
        storey_id=storey_id,
        is_stack_root=True,
    )
    for (label, fixture_id), point in zip(labels[1:], points[1:]):
        tree.nodes[label] = MergeNode(
            id=label,
            position=point,
            storey_id=storey_id,
            fixture_id=fixture_id,
        )

    edges = _prim_mst(points, root_index=0)
    # Prim edges are (parent, child) in tree order.
    for parent_idx, child_idx in edges:
        parent_label = labels[parent_idx][0]
        child_label = labels[child_idx][0]
        tree.nodes[child_label].parent = parent_label
        tree.nodes[parent_label].children.append(child_label)

    return tree


def annotate_cumulative_du(
    tree: MergeTree,
    fixtures_by_id: Dict[str, Fixture],
) -> None:
    """Fills each node's ``cumulative_du`` with the sum of downstream
    fixture DUs. The traversal is post-order, so children are resolved
    before their parents.
    """
    visited: set[str] = set()

    def visit(node_id: str) -> float:
        if node_id in visited:
            return tree.nodes[node_id].cumulative_du
        visited.add(node_id)
        node = tree.nodes[node_id]
        total = 0.0
        if node.fixture_id is not None:
            fx = fixtures_by_id.get(node.fixture_id)
            if fx is not None:
                total += fx.discharge_unit
        for child_id in node.children:
            total += visit(child_id)
        node.cumulative_du = total
        return total

    visit(tree.root_id)
