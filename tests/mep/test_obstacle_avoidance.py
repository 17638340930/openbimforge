"""Structural beam avoidance tests.

When a storey carries an ``Obstacle`` polygon between a fixture and its
stack, the A* router must produce a branch path that avoids it. These
tests pin that contract by placing a beam in the direct line of sight
and asserting the routed pipe does not cross it.
"""

import pytest

from forge_core.mep_agent import Obstacle
from forge_core.mep_agent.fixture_placer import place_fixtures
from forge_core.mep_agent.pipe_router import route_branches
from forge_core.mep_agent.schema import point_in_polygon
from forge_core.mep_agent.stack_planner import plan_stacks


@pytest.fixture
def building_with_beam(multi_storey_office_building):
    # Plant a beam across the L1 ceiling void, running east-west through
    # the northern section of the slab (outside the shaft so the stack
    # can still root there). Any branch from the male restroom on the
    # south to the central shaft would naively cross this beam.
    building = multi_storey_office_building
    beam = Obstacle(
        id="beam_L1",
        polygon=[
            (14000.0, 13500.0),
            (28000.0, 13500.0),
            (28000.0, 14000.0),
            (14000.0, 14000.0),
        ],
        kind="beam",
    )
    building.storeys[0].obstacles.append(beam)
    return building


def test_routing_avoids_beam_interior(building_with_beam):
    fixtures = place_fixtures(building_with_beam)
    stacks = plan_stacks(building_with_beam, fixtures)
    pipes, warnings = route_branches(building_with_beam, fixtures, stacks)

    assert not warnings, f"unexpected router warnings: {warnings}"

    # Sample every pipe segment at a few intermediate points and make
    # sure none land inside the (un-inflated) beam polygon. Endpoints
    # may legitimately touch the beam edge; the interior check is what
    # matters for collision purposes.
    beam_polygon = building_with_beam.storeys[0].obstacles[0].polygon
    for seg in pipes:
        if seg.kind not in {"branch", "trunk"}:
            continue
        for t in (0.25, 0.5, 0.75):
            x = seg.start[0] + (seg.end[0] - seg.start[0]) * t
            y = seg.start[1] + (seg.end[1] - seg.start[1]) * t
            assert not point_in_polygon(
                (x, y), beam_polygon
            ), f"segment {seg.id} crosses the beam at ({x:.0f}, {y:.0f})"
