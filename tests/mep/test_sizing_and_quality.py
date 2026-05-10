"""Sizing table + quality evaluator sanity checks."""

import pytest

from forge_core.mep_agent.mep_pipeline import run_mep_pipeline
from forge_core.mep_agent.sizing import _pick_diameter


@pytest.mark.parametrize(
    "du,expected",
    [
        (0.5, 50),
        (3.0, 50),
        (8.0, 75),
        (20.0, 100),
        (80.0, 150),
        (500.0, 200),
    ],
)
def test_branch_diameter_sizing(du, expected):
    assert _pick_diameter(du, "soil_branch") == expected


def test_full_pipeline_quality_is_reasonable(multi_storey_office_building):
    result = run_mep_pipeline(multi_storey_office_building)
    quality = result["quality"]
    assert quality["quality_score"] >= 60
    # Connectivity must be perfect for a well-conditioned floor plan.
    assert quality["dimensions"]["connectivity"]["score"] == 100
    # At least one stack was vented.
    assert quality["dimensions"]["code_compliance"]["vented_stacks"] >= 1
