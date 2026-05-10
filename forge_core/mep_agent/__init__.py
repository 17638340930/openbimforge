"""
openBIMForge MEP Agent.

A dedicated generation pipeline for mechanical / plumbing systems that plugs
into the openBIMForge Nexus framework. The initial release focuses on the
**sanitary drainage system** (toilets, floor drains, wash basins, kitchen
sinks), including:

- Stage B: rule-based fixture placement inside known room polygons.
- Stage C: vertical soil-stack planning via clustering.
- Stage D: A* horizontal pipe routing in the ceiling void.
- Stage E: diameter sizing (GB 50015), venting stubs, cleanout insertion.

The module exposes `run_mep_pipeline(building_plan)` which returns a
`MepPlan` dataclass and can optionally emit IFC4 / Vectorworks Python
artifacts. The pipeline is self-contained: it only depends on the
`knowledge` package for the fixture catalog and on the Python standard
library.
"""

from .schema import (
    BuildingPlan,
    Fixture,
    MepPlan,
    Obstacle,
    PipeSegment,
    Room,
    Shaft,
    Stack,
    Storey,
)
from .mep_pipeline import run_mep_pipeline
from .quality import evaluate_mep_quality

__all__ = [
    "BuildingPlan",
    "Fixture",
    "MepPlan",
    "Obstacle",
    "PipeSegment",
    "Room",
    "Shaft",
    "Stack",
    "Storey",
    "evaluate_mep_quality",
    "run_mep_pipeline",
]
