"""Shared pytest fixtures for the MEP agent test suite.

Each fixture returns a fully materialised `BuildingPlan` so individual
stage tests can focus on behaviour rather than wiring.
"""

from __future__ import annotations

import pytest

from forge_core.mep_agent.schema import BuildingPlan, Room, Shaft, Storey


@pytest.fixture
def single_bathroom_building() -> BuildingPlan:
    """A minimal single-storey building with one bathroom, no shafts."""
    room = Room(
        id="bath_L1",
        storey_id="L1",
        type="bathroom",
        polygon=[(0.0, 0.0), (3000.0, 0.0), (3000.0, 2500.0), (0.0, 2500.0)],
        door=(1500.0, 0.0),
    )
    storey = Storey(
        id="L1",
        index=0,
        elevation_mm=0.0,
        height_mm=3000.0,
        outline=[(-2000.0, -2000.0), (5000.0, -2000.0), (5000.0, 4500.0), (-2000.0, 4500.0)],
        rooms=[room],
    )
    return BuildingPlan(project_name="unit-test-bathroom", storeys=[storey], roof_elevation_mm=3300.0)


@pytest.fixture
def multi_storey_office_building() -> BuildingPlan:
    """Two-storey office with male/female public restrooms and a centre shaft."""
    storeys = []
    for idx, elev in enumerate((0.0, 3600.0)):
        storey_id = f"L{idx + 1}"
        rooms = [
            Room(
                id=f"wc_m_{storey_id}",
                storey_id=storey_id,
                type="restroom_public_male",
                polygon=[(19000.0, 6000.0), (24000.0, 6000.0), (24000.0, 9500.0), (19000.0, 9500.0)],
                door=(19200.0, 9500.0),
            ),
            Room(
                id=f"wc_f_{storey_id}",
                storey_id=storey_id,
                type="restroom_public_female",
                polygon=[(19000.0, 9500.0), (24000.0, 9500.0), (24000.0, 14000.0), (19000.0, 14000.0)],
                door=(19200.0, 9500.0),
            ),
        ]
        shafts = [
            Shaft(
                id="shaft_center",
                polygon=[(17000.0, 8500.0), (19000.0, 8500.0), (19000.0, 11500.0), (17000.0, 11500.0)],
            )
        ]
        storeys.append(
            Storey(
                id=storey_id,
                index=idx,
                elevation_mm=elev,
                height_mm=3600.0,
                outline=[(0.0, 0.0), (36000.0, 0.0), (36000.0, 20000.0), (0.0, 20000.0)],
                rooms=rooms,
                shafts=shafts,
            )
        )
    return BuildingPlan(
        project_name="unit-test-office",
        storeys=storeys,
        roof_elevation_mm=7500.0,
    )
