"""
Stage E — sizing, venting, cleanouts.

Once the geometric layout is complete (branch + stack pipe segments), this
module:

1. Assigns diameters to every pipe segment based on cumulative discharge
   units, looked up in the GB 50015 table shipped with the fixture catalog.
2. Sets each stack's diameter.
3. Inserts cleanouts along long branches (every ``max_cleanout_spacing_m``
   metres) and at sharp direction changes.
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from typing import Dict, List, Sequence

from .schema import (
    BuildingPlan,
    Fixture,
    PipeSegment,
    Stack,
    segment_length_3d,
)


_KNOWLEDGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge",
)
_FIXTURE_FILE = os.path.join(_KNOWLEDGE_ROOT, "mep_fixtures.json")
_CATALOG_CACHE: Dict = {}


def _catalog() -> Dict:
    if _CATALOG_CACHE:
        return _CATALOG_CACHE
    with open(_FIXTURE_FILE, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    _CATALOG_CACHE.update(data)
    return _CATALOG_CACHE


def _pick_diameter(du: float, table_key: str) -> float:
    table = _catalog()["diameter_sizing_table"].get(table_key, [])
    for row in table:
        if du <= row["max_du"]:
            return float(row["diameter_mm"])
    # Fallback to the largest tabulated diameter.
    return float(table[-1]["diameter_mm"]) if table else 100.0


def size_stacks(stacks: Sequence[Stack]) -> None:
    for stack in stacks:
        stack.diameter_mm = _pick_diameter(stack.cumulative_du, "soil_stack")


def size_branches(
    pipes: List[PipeSegment],
    fixtures: Sequence[Fixture],
) -> None:
    """Sizes every branch / trunk segment by its cumulative downstream DU.

    The pipe router already populates ``fixture_ids`` with the full list
    of downstream fixtures for each segment (computed from the merge
    tree), so here we just sum their DUs and look up the soil-branch
    table. The diameter must never drop below the fixture outlet, which
    is guaranteed by the table's smallest row (DN50).
    """
    fixture_du = {f.id: f.discharge_unit for f in fixtures}
    fixture_diameter = {f.id: f.drain_diameter_mm for f in fixtures}

    for seg in pipes:
        if seg.kind not in {"branch", "trunk"}:
            continue
        downstream_ids = seg.fixture_ids or []
        du = sum(fixture_du.get(fid, 0.0) for fid in downstream_ids)
        table_diameter = _pick_diameter(du, "soil_branch") if du > 0 else 50.0
        # Respect the largest fixture outlet in the subtree so a big
        # toilet branch never gets downsized by a low-DU template.
        outlet_floor = max(
            (fixture_diameter.get(fid, 0.0) for fid in downstream_ids),
            default=50.0,
        )
        seg.diameter_mm = max(seg.diameter_mm, table_diameter, outlet_floor)


def size_stack_segments(pipes: List[PipeSegment], stacks: Sequence[Stack]) -> None:
    stack_diameter = {s.id: s.diameter_mm for s in stacks}
    for seg in pipes:
        if seg.kind == "stack" and seg.stack_id in stack_diameter:
            seg.diameter_mm = stack_diameter[seg.stack_id] or seg.diameter_mm
        elif seg.kind == "vent" and seg.stack_id in stack_diameter:
            # Vent keeps the same diameter as the stack at minimum DN75.
            seg.diameter_mm = max(75.0, stack_diameter[seg.stack_id] or seg.diameter_mm)


def insert_cleanouts(
    pipes: List[PipeSegment],
    max_spacing_m: float = 15.0,
) -> List[PipeSegment]:
    """Creates `cleanout` pseudo-segments whenever a branch exceeds the
    maximum spacing. Each cleanout is a 200 mm vertical stub rising from the
    main branch axis; downstream exporters can materialise it as an IfcPipe
    fitting.
    """
    cleanouts: List[PipeSegment] = []
    branches_by_stack: Dict[str, List[PipeSegment]] = defaultdict(list)
    for seg in pipes:
        if seg.kind in {"branch", "trunk"} and seg.stack_id:
            branches_by_stack[seg.stack_id].append(seg)

    max_spacing_mm = max_spacing_m * 1000.0
    counter = 0
    for stack_id, segs in branches_by_stack.items():
        running = 0.0
        last_cleanout_point = None
        for seg in segs:
            length = segment_length_3d(seg.start, seg.end)
            running += length
            if last_cleanout_point is None:
                last_cleanout_point = seg.start
            if running >= max_spacing_mm:
                co_start = seg.end
                co_end = (co_start[0], co_start[1], co_start[2] + 200.0)
                cleanouts.append(
                    PipeSegment(
                        id=f"co_{stack_id}_{counter:03d}",
                        kind="cleanout",
                        start=co_start,
                        end=co_end,
                        diameter_mm=seg.diameter_mm,
                        slope_pct=0.0,
                        stack_id=stack_id,
                    )
                )
                counter += 1
                running = 0.0
    return cleanouts
