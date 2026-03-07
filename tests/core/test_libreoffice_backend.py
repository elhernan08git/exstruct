"""Tests for the LibreOffice rich extraction backend."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess
from typing import cast
from xml.etree import ElementTree

from _pytest.monkeypatch import MonkeyPatch
import pytest

from exstruct.core.backends.libreoffice_backend import LibreOfficeRichBackend
from exstruct.core.libreoffice import (
    LibreOfficeChartGeometry,
    LibreOfficeDrawPageShape,
    LibreOfficeSession,
    LibreOfficeSessionConfig,
    LibreOfficeUnavailableError,
    _resolve_python_path,
)
from exstruct.core.ooxml_drawing import (
    DrawingConnectorRef,
    DrawingShapeRef,
    OoxmlConnectorInfo,
    OoxmlShapeInfo,
    SheetDrawingData,
    _parse_connector_node,
)
from exstruct.models import Arrow, Shape


class _DummySession:
    """Dummy LibreOffice session used in tests."""

    def __enter__(self) -> _DummySession:
        """Return the test double as the context-manager result."""

        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Accept context-manager exit arguments without suppressing errors."""

        _ = exc_type
        _ = exc
        _ = tb

    def load_workbook(self, file_path: Path) -> object:
        """Return a lightweight workbook token for tests."""

        return {"file_path": str(file_path)}

    def close_workbook(self, workbook: object) -> None:
        """Accept a workbook token without additional cleanup."""

        _ = workbook

    def extract_chart_geometries(
        self, file_path: Path
    ) -> dict[str, list[LibreOfficeChartGeometry]]:
        """Provide chart geometry data for this test double."""

        _ = file_path
        return {}

    def extract_draw_page_shapes(
        self, file_path: Path
    ) -> dict[str, list[LibreOfficeDrawPageShape]]:
        """Provide draw-page shape data for this test double."""

        _ = file_path
        return {}


def _dummy_session_factory() -> LibreOfficeSession:
    """Return a dummy LibreOffice session test double."""

    return cast(LibreOfficeSession, _DummySession())


class _ChartGeometrySession(_DummySession):
    """Session double that returns fixed chart geometry data."""

    def extract_chart_geometries(
        self, file_path: Path
    ) -> dict[str, list[LibreOfficeChartGeometry]]:
        """Provide chart geometry data for this test double."""

        _ = file_path
        return {
            "Sheet1": [
                LibreOfficeChartGeometry(
                    name="グラフ 1",
                    persist_name="Object 1",
                    left=370,
                    top=26,
                    width=351,
                    height=214,
                )
            ]
        }


def _chart_geometry_session_factory() -> LibreOfficeSession:
    """Return a LibreOffice session double with chart geometries."""

    return cast(LibreOfficeSession, _ChartGeometrySession())


class _DrawPageSession(_DummySession):
    """Session double that returns fixed draw-page shapes."""

    def __init__(self, payload: dict[str, list[LibreOfficeDrawPageShape]]) -> None:
        """Initialize the test double."""

        self._payload = payload

    def extract_draw_page_shapes(
        self, file_path: Path
    ) -> dict[str, list[LibreOfficeDrawPageShape]]:
        """Provide draw-page shape data for this test double."""

        _ = file_path
        return self._payload


def test_libreoffice_backend_extracts_connector_graph_from_sample() -> None:
    """Verify that LibreOffice backend extracts connector graph from sample."""

    backend = LibreOfficeRichBackend(
        Path("sample/flowchart/sample-shape-connector.xlsx"),
        session_factory=_dummy_session_factory,
    )
    shape_data = backend.extract_shapes(mode="libreoffice")
    assert shape_data
    first_sheet = next(iter(shape_data.values()))
    connectors = [shape for shape in first_sheet if isinstance(shape, Arrow)]
    resolved = [
        connector
        for connector in connectors
        if connector.begin_id is not None and connector.end_id is not None
    ]
    assert len(connectors) >= 10
    assert len(resolved) >= 10
    assert all(connector.provenance == "libreoffice_uno" for connector in resolved)


def test_libreoffice_backend_extracts_chart_from_sample() -> None:
    """Verify that LibreOffice backend extracts chart from sample."""

    backend = LibreOfficeRichBackend(
        Path("sample/basic/sample.xlsx"),
        session_factory=_chart_geometry_session_factory,
    )
    chart_data = backend.extract_charts(mode="libreoffice")
    charts = chart_data["Sheet1"]
    assert len(charts) >= 1
    chart = charts[0]
    assert chart.title == "売上データ"
    assert len(chart.series) == 3
    assert (chart.l, chart.t, chart.w, chart.h) == (370, 26, 351, 214)
    assert chart.provenance == "libreoffice_uno"
    assert chart.approximation_level == "partial"
    assert chart.confidence == 0.8


def test_libreoffice_backend_uses_draw_page_shapes_without_ooxml(
    monkeypatch: MonkeyPatch,
) -> None:
    """Verify that LibreOffice backend uses draw page shapes without OOXML."""

    payload = {
        "Sheet1": [
            LibreOfficeDrawPageShape(
                name="Start",
                shape_type="com.sun.star.drawing.CustomShape",
                text="S",
                left=10,
                top=20,
                width=30,
                height=40,
            ),
            LibreOfficeDrawPageShape(
                name="Connector",
                shape_type="com.sun.star.drawing.ConnectorShape",
                left=40,
                top=30,
                width=50,
                height=60,
                is_connector=True,
                start_shape_name="Start",
                end_shape_name="End",
            ),
            LibreOfficeDrawPageShape(
                name="End",
                shape_type="com.sun.star.drawing.CustomShape",
                text="E",
                left=100,
                top=120,
                width=30,
                height=40,
            ),
        ]
    }
    monkeypatch.setattr(
        "exstruct.core.backends.libreoffice_backend.read_sheet_drawings",
        lambda _path: {"Sheet1": SheetDrawingData()},
    )
    backend = LibreOfficeRichBackend(
        Path("sample/flowchart/sample-shape-connector.xlsx"),
        session_factory=lambda: cast(LibreOfficeSession, _DrawPageSession(payload)),
    )

    shape_data = backend.extract_shapes(mode="libreoffice")

    items = shape_data["Sheet1"]
    assert [item.kind for item in items] == ["shape", "arrow", "shape"]
    first_shape = cast(Shape, items[0])
    connector = cast(Arrow, items[1])
    second_shape = cast(Shape, items[2])
    assert first_shape.id == 1
    assert first_shape.type == "CustomShape"
    assert second_shape.id == 2
    assert connector.begin_id == 1
    assert connector.end_id == 2
    assert connector.approximation_level == "direct"
    assert connector.confidence == 0.9


def test_libreoffice_backend_prefers_ooxml_refs_over_uno_direct_refs(
    monkeypatch: MonkeyPatch,
) -> None:
    """Verify that LibreOffice backend prefers OOXML refs over uno direct refs."""

    payload = {
        "Sheet1": [
            LibreOfficeDrawPageShape(
                name="Start",
                shape_type="com.sun.star.drawing.CustomShape",
                left=10,
                top=20,
                width=30,
                height=40,
            ),
            LibreOfficeDrawPageShape(
                name="Connector",
                shape_type="com.sun.star.drawing.ConnectorShape",
                left=40,
                top=30,
                width=50,
                height=60,
                is_connector=True,
                start_shape_name="Start",
                end_shape_name="End",
            ),
            LibreOfficeDrawPageShape(
                name="End",
                shape_type="com.sun.star.drawing.CustomShape",
                left=100,
                top=120,
                width=30,
                height=40,
            ),
        ]
    }
    monkeypatch.setattr(
        "exstruct.core.backends.libreoffice_backend.read_sheet_drawings",
        lambda _path: {
            "Sheet1": SheetDrawingData(
                shapes=[
                    OoxmlShapeInfo(
                        ref=DrawingShapeRef(
                            drawing_id=10,
                            name="Start",
                            kind="shape",
                            left=10,
                            top=20,
                            width=30,
                            height=40,
                        )
                    ),
                    OoxmlShapeInfo(
                        ref=DrawingShapeRef(
                            drawing_id=20,
                            name="End",
                            kind="shape",
                            left=100,
                            top=120,
                            width=30,
                            height=40,
                        )
                    ),
                ],
                connectors=[
                    OoxmlConnectorInfo(
                        ref=DrawingShapeRef(
                            drawing_id=30,
                            name="Connector",
                            kind="connector",
                            left=40,
                            top=30,
                            width=50,
                            height=60,
                        ),
                        connection=DrawingConnectorRef(
                            drawing_id=30,
                            start_drawing_id=20,
                            end_drawing_id=10,
                        ),
                    )
                ],
            )
        },
    )
    backend = LibreOfficeRichBackend(
        Path("sample/flowchart/sample-shape-connector.xlsx"),
        session_factory=lambda: cast(LibreOfficeSession, _DrawPageSession(payload)),
    )

    shape_data = backend.extract_shapes(mode="libreoffice")

    connector = next(
        shape for shape in shape_data["Sheet1"] if isinstance(shape, Arrow)
    )
    assert connector.begin_id == 2
    assert connector.end_id == 1
    assert connector.approximation_level == "direct"
    assert connector.confidence == 1.0


def test_ooxml_connector_tail_end_maps_to_begin_arrow_style() -> None:
    """Verify that OOXML connector tail end maps to begin arrow style."""

    node = ElementTree.fromstring(
        """
        <xdr:cxnSp xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
                   xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <xdr:nvCxnSpPr>
            <xdr:cNvPr id="7" name="Connector 1" />
            <xdr:cNvCxnSpPr />
          </xdr:nvCxnSpPr>
          <xdr:spPr>
            <a:xfrm>
              <a:off x="0" y="0" />
              <a:ext cx="12700" cy="12700" />
            </a:xfrm>
            <a:ln>
              <a:tailEnd type="triangle" />
            </a:ln>
          </xdr:spPr>
        </xdr:cxnSp>
        """
    )
    connector = _parse_connector_node(node)
    assert connector is not None
    assert connector.begin_arrow_style == 2
    assert connector.end_arrow_style is None


def test_ooxml_connector_head_end_maps_to_end_arrow_style() -> None:
    """Verify that OOXML connector head end maps to end arrow style."""

    node = ElementTree.fromstring(
        """
        <xdr:cxnSp xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
                   xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <xdr:nvCxnSpPr>
            <xdr:cNvPr id="7" name="Connector 1" />
            <xdr:cNvCxnSpPr />
          </xdr:nvCxnSpPr>
          <xdr:spPr>
            <a:xfrm>
              <a:off x="0" y="0" />
              <a:ext cx="12700" cy="12700" />
            </a:xfrm>
            <a:ln>
              <a:headEnd type="triangle" />
            </a:ln>
          </xdr:spPr>
        </xdr:cxnSp>
        """
    )
    connector = _parse_connector_node(node)
    assert connector is not None
    assert connector.begin_arrow_style is None
    assert connector.end_arrow_style == 2


def test_libreoffice_session_cleans_temp_profile_on_enter_failure(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that LibreOffice session cleans temp profile on enter failure."""

    removed_paths: list[Path] = []
    created_dir = tmp_path / "lo-profile"
    soffice_path = tmp_path / "soffice.exe"
    python_path = tmp_path / "python.exe"
    soffice_path.write_text("", encoding="utf-8")
    python_path.write_text("", encoding="utf-8")

    def _fake_mkdtemp(*, prefix: str, temp_dir: str | None = None) -> str:
        """Provide a fake mkdtemp implementation for this test."""

        _ = prefix
        _ = temp_dir
        created_dir.mkdir(parents=True, exist_ok=True)
        return str(created_dir)

    def _fake_rmtree(path: Path | str, *, ignore_errors: bool) -> None:
        """Provide a fake rmtree implementation for this test."""

        _ = ignore_errors
        removed_paths.append(Path(path))

    def _fake_run(*_args: object, **_kwargs: object) -> object:
        """Provide a fake run implementation for this test."""

        raise subprocess.TimeoutExpired(cmd="soffice --version", timeout=1.0)

    monkeypatch.setattr(
        "exstruct.core.libreoffice.mkdtemp",
        cast(Callable[..., str], _fake_mkdtemp),
    )
    monkeypatch.setattr("exstruct.core.libreoffice.shutil.rmtree", _fake_rmtree)
    monkeypatch.setattr("exstruct.core.libreoffice.subprocess.run", _fake_run)

    session = LibreOfficeSession(
        LibreOfficeSessionConfig(
            soffice_path=soffice_path,
            startup_timeout_sec=1.0,
            exec_timeout_sec=1.0,
            profile_root=None,
        )
    )

    with pytest.raises(LibreOfficeUnavailableError):
        session.__enter__()

    assert removed_paths == [created_dir]
    assert session._temp_profile_dir is None


def test_resolve_python_path_prefers_override(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that an explicit Python override wins over auto-detection."""

    override_path = tmp_path / "custom-python"
    override_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("EXSTRUCT_LIBREOFFICE_PYTHON_PATH", str(override_path))

    assert _resolve_python_path(tmp_path / "soffice") == override_path


def test_resolve_python_path_checks_resolved_soffice_dir(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that bundled Python lookup follows the real soffice program directory."""

    real_program_dir = tmp_path / "real-program"
    real_program_dir.mkdir()
    real_soffice = real_program_dir / "soffice"
    real_soffice.write_text("", encoding="utf-8")
    real_python = real_program_dir / "python.bin"
    real_python.write_text("", encoding="utf-8")

    soffice_path = tmp_path / "bin" / "soffice"
    soffice_path.parent.mkdir(parents=True)
    soffice_path.write_text("", encoding="utf-8")

    original_resolve = Path.resolve

    def _fake_resolve(self: Path, *, strict: bool = False) -> Path:
        if self == soffice_path:
            return real_soffice
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", _fake_resolve)

    assert _resolve_python_path(soffice_path) == real_python


def test_resolve_python_path_falls_back_to_system_python(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that Debian/Ubuntu-style system Python fallback is supported."""

    soffice_path = tmp_path / "soffice"
    soffice_path.write_text("", encoding="utf-8")
    venv_python = tmp_path / "venv-python"
    venv_python.write_text("", encoding="utf-8")
    system_python = tmp_path / "system-python"
    system_python.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "exstruct.core.libreoffice._system_python_candidates",
        lambda: (venv_python, system_python),
    )
    monkeypatch.setattr(
        "exstruct.core.libreoffice._python_supports_libreoffice_bridge",
        lambda path: path == system_python,
    )

    assert _resolve_python_path(soffice_path) == system_python


def test_resolve_python_path_returns_none_without_compatible_python(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that auto-detection rejects Python candidates without UNO support."""

    soffice_path = tmp_path / "soffice"
    soffice_path.write_text("", encoding="utf-8")
    candidate = tmp_path / "python3"
    candidate.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "exstruct.core.libreoffice._system_python_candidates",
        lambda: (candidate,),
    )
    monkeypatch.setattr(
        "exstruct.core.libreoffice._python_supports_libreoffice_bridge",
        lambda _path: False,
    )

    assert _resolve_python_path(soffice_path) is None


def test_libreoffice_session_exit_cleans_profile_even_if_kill_wait_times_out(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that LibreOffice session exit cleans profile even if kill wait times out."""

    cleaned_paths: list[Path] = []

    class _FakeProcess:
        """Fake LibreOffice process used to test shutdown behavior."""

        def __init__(self) -> None:
            """Initialize the test double."""

            self.terminate_called = False
            self.kill_called = False
            self.wait_calls = 0

        def terminate(self) -> None:
            """Record a termination request on the fake process."""

            self.terminate_called = True

        def wait(self, *, timeout: float) -> None:
            """Simulate waiting for the fake process and raise a timeout."""

            _ = timeout
            self.wait_calls += 1
            raise subprocess.TimeoutExpired(cmd="soffice", timeout=5.0)

        def kill(self) -> None:
            """Record a forced kill request on the fake process."""

            self.kill_called = True

    def _fake_cleanup(path: Path) -> None:
        """Provide a fake cleanup implementation for this test."""

        cleaned_paths.append(path)

    session = LibreOfficeSession(
        LibreOfficeSessionConfig(
            soffice_path=tmp_path / "soffice.exe",
            startup_timeout_sec=1.0,
            exec_timeout_sec=1.0,
            profile_root=None,
        )
    )
    profile_dir = tmp_path / "lo-profile"
    process = _FakeProcess()
    session._temp_profile_dir = profile_dir
    session._soffice_process = cast(subprocess.Popen[str], process)
    session._accept_port = 12345
    monkeypatch.setattr("exstruct.core.libreoffice._cleanup_profile_dir", _fake_cleanup)

    session.__exit__(None, None, None)

    assert process.terminate_called is True
    assert process.kill_called is True
    assert process.wait_calls == 2
    assert cleaned_paths == [profile_dir]
    assert session._soffice_process is None
    assert session._temp_profile_dir is None
    assert session._accept_port is None
