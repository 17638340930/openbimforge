"""IFC exporter should round-trip the pipe segments into a readable file."""

from __future__ import annotations

import re
from pathlib import Path

from forge_core.mep_agent.ifc_exporter import export_mep_to_ifc
from forge_core.mep_agent.mep_pipeline import run_mep_pipeline


def test_ifc_contains_matching_pipe_segment_count(tmp_path: Path, multi_storey_office_building):
    result = run_mep_pipeline(multi_storey_office_building)
    plan = result["plan"]

    out_path = tmp_path / "out.ifc"
    written = export_mep_to_ifc(multi_storey_office_building, plan, str(out_path))
    assert Path(written).exists()

    body = out_path.read_text(encoding="utf-8")
    assert body.startswith("ISO-10303-21")
    assert body.rstrip().endswith("END-ISO-10303-21;")
    # SPF uses upper-case entity names.
    pipe_entity_count = len(re.findall(r"IFCPIPESEGMENT\(", body))
    assert pipe_entity_count == len(plan.pipes)
