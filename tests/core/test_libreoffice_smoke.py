from pathlib import Path

import pytest

from exstruct import extract
from exstruct.models import Arrow

pytestmark = pytest.mark.libreoffice


def test_libreoffice_mode_smoke_extracts_sample_shapes_and_charts() -> None:
    flowchart = extract(
        Path("sample/flowchart/sample-shape-connector.xlsx"),
        mode="libreoffice",
    )
    flowchart_sheet = next(iter(flowchart.sheets.values()))
    connectors = [shape for shape in flowchart_sheet.shapes if isinstance(shape, Arrow)]
    resolved = [
        connector
        for connector in connectors
        if connector.begin_id is not None and connector.end_id is not None
    ]
    assert resolved

    basic = extract(Path("sample/basic/sample.xlsx"), mode="libreoffice")
    basic_sheet = basic["Sheet1"]
    assert basic_sheet.charts
    chart = basic_sheet.charts[0]
    assert chart.title
    assert chart.chart_type == "Line"
    assert len(chart.series) == 3
