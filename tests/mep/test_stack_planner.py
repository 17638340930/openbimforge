"""Stack planner should return at least one stack and assign every fixture
to a stack cluster."""

from forge_core.mep_agent.fixture_placer import place_fixtures
from forge_core.mep_agent.stack_planner import plan_stacks


def test_plan_stacks_has_at_least_one_cluster(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    stacks = plan_stacks(multi_storey_office_building, fixtures)
    assert stacks, "pipeline must produce at least one stack"


def test_every_fixture_is_assigned(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    stacks = plan_stacks(multi_storey_office_building, fixtures)
    assigned = set()
    for stack in stacks:
        assigned.update(stack.fixture_ids)
    fixture_ids = {fx.id for fx in fixtures}
    assert assigned == fixture_ids


def test_stack_elevation_spans_building(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    stacks = plan_stacks(multi_storey_office_building, fixtures)
    for stack in stacks:
        # Base below every fixture, top above the configured roof elevation.
        fixture_elevations = [fx.elevation_mm for fx in fixtures if fx.id in stack.fixture_ids]
        assert stack.base_elevation_mm < min(fixture_elevations)
        assert stack.top_elevation_mm > max(fixture_elevations)
