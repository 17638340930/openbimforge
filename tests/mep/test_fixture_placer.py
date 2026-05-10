"""Rule-based fixture placement should drop one fixture per slot defined in
the room template, keeping them inside the room polygon."""

from forge_core.mep_agent.fixture_placer import place_fixtures
from forge_core.mep_agent.schema import point_in_polygon


def test_bathroom_yields_three_fixtures(single_bathroom_building):
    fixtures = place_fixtures(single_bathroom_building)
    kinds = sorted(fx.type for fx in fixtures)
    assert kinds == ["floor_drain", "toilet", "wash_basin"]


def test_fixtures_sit_inside_room(single_bathroom_building):
    room_polygon = single_bathroom_building.storeys[0].rooms[0].polygon
    for fx in place_fixtures(single_bathroom_building):
        assert point_in_polygon(fx.position, room_polygon), (
            f"fixture {fx.id} of type {fx.type} fell outside the room polygon"
        )


def test_restroom_template_counts(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    per_type_per_storey: dict[tuple[str, str], int] = {}
    for fx in fixtures:
        key = (fx.storey_id, fx.type)
        per_type_per_storey[key] = per_type_per_storey.get(key, 0) + 1

    # Per GB 50015 template shipped with mep_fixtures.json:
    # male 2T+3U+2W+1D, female 4T+2W+1D  -> per storey: T=6, U=3, W=4, D=2
    for storey in ("L1", "L2"):
        assert per_type_per_storey[(storey, "toilet")] == 6
        assert per_type_per_storey[(storey, "urinal")] == 3
        assert per_type_per_storey[(storey, "wash_basin")] == 4
        assert per_type_per_storey[(storey, "floor_drain")] == 2
