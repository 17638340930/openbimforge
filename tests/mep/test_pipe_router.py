"""The A* branch router should connect every fixture to its stack without
warnings in a well-conditioned input."""

from forge_core.mep_agent.fixture_placer import place_fixtures
from forge_core.mep_agent.pipe_router import build_stack_segments, route_branches
from forge_core.mep_agent.stack_planner import plan_stacks


def test_routing_produces_segments_for_every_fixture(single_bathroom_building):
    fixtures = place_fixtures(single_bathroom_building)
    stacks = plan_stacks(single_bathroom_building, fixtures)
    pipes, warnings = route_branches(single_bathroom_building, fixtures, stacks)
    assert not warnings, f"unexpected router warnings: {warnings}"
    routed_fixtures = set()
    for seg in pipes:
        routed_fixtures.update(seg.fixture_ids)
    assert routed_fixtures == {fx.id for fx in fixtures}


def test_branch_slope_is_within_spec(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    stacks = plan_stacks(multi_storey_office_building, fixtures)
    pipes, _ = route_branches(multi_storey_office_building, fixtures, stacks)
    for seg in pipes:
        if seg.kind != "branch":
            continue
        assert 0.0 < seg.slope_pct <= 5.0, (
            f"segment {seg.id} has non-physical slope {seg.slope_pct}%"
        )


def test_stack_segments_are_vertical(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    stacks = plan_stacks(multi_storey_office_building, fixtures)
    stack_pipes = build_stack_segments(multi_storey_office_building, stacks)
    assert stack_pipes, "build_stack_segments must emit at least one segment"
    for seg in stack_pipes:
        if seg.kind == "stack":
            assert seg.start[0] == seg.end[0] and seg.start[1] == seg.end[1]
            assert seg.end[2] > seg.start[2]
