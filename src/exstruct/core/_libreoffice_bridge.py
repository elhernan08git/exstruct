from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Protocol, cast

import uno

_HMM_PER_POINT = 2540.0 / 72.0


class _ServiceManager(Protocol):
    def createInstanceWithContext(  # noqa: N802
        self, service_name: str, context: object
    ) -> object: ...


class _UnoContext(Protocol):
    ServiceManager: _ServiceManager


class _UnoResolver(Protocol):
    def resolve(self, connection: str) -> object: ...


class _Desktop(Protocol):
    def loadComponentFromURL(  # noqa: N802
        self,
        url: str,
        target: str,
        search_flags: int,
        properties: tuple[object, ...],
    ) -> object: ...


class _NamedContainer(Protocol):
    def getElementNames(self) -> list[str]: ...  # noqa: N802


class _DrawPage(Protocol):
    def getCount(self) -> int: ...  # noqa: N802

    def getByIndex(self, index: int) -> object: ...  # noqa: N802


class _ShapeLike(Protocol):
    def getShapeType(self) -> str: ...  # noqa: N802


class _Sheet(Protocol):
    def getCharts(self) -> _NamedContainer: ...  # noqa: N802

    def getDrawPage(self) -> _DrawPage: ...  # noqa: N802


class _Sheets(Protocol):
    def getElementNames(self) -> list[str]: ...  # noqa: N802

    def getByName(self, name: str) -> object: ...  # noqa: N802


class _SpreadsheetDocument(Protocol):
    def getSheets(self) -> _Sheets: ...  # noqa: N802

    def close(self, deliver_ownership: bool) -> None: ...

    def dispose(self) -> None: ...


def main() -> int:
    args = _parse_args()
    ctx = _resolve_context(args.host, args.port)
    desktop = cast(
        _Desktop,
        ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx),
    )
    doc = _load_document(desktop, Path(args.file))
    try:
        if args.kind == "draw-page":
            payload = _extract_draw_page_payload(doc)
        else:
            payload = _extract_chart_payload(doc)
    finally:
        _close_document(doc)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--file", required=True)
    parser.add_argument("--kind", choices=("charts", "draw-page"), default="charts")
    return parser.parse_args()


def _resolve_context(host: str, port: int) -> _UnoContext:
    local_ctx = uno.getComponentContext()
    resolver = cast(
        _UnoResolver,
        local_ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver",
            local_ctx,
        ),
    )
    connection = f"uno:socket,host={host},port={port};urp;StarOffice.ComponentContext"
    deadline = time.monotonic() + 15.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return cast(_UnoContext, resolver.resolve(connection))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to resolve LibreOffice UNO context.")


def _load_document(desktop: _Desktop, file_path: Path) -> _SpreadsheetDocument:
    from com.sun.star.beans import PropertyValue

    props: list[object] = []
    for name, value in (("Hidden", True), ("ReadOnly", True)):
        prop = PropertyValue()
        prop.Name = name
        prop.Value = value
        props.append(prop)
    return cast(
        _SpreadsheetDocument,
        desktop.loadComponentFromURL(
            uno.systemPathToFileUrl(str(file_path.resolve())),
            "_blank",
            0,
            tuple(props),
        ),
    )


def _extract_chart_payload(doc: _SpreadsheetDocument) -> dict[str, object]:
    sheets_payload: dict[str, list[dict[str, object]]] = {}
    sheets = doc.getSheets()
    for sheet_name in sheets.getElementNames():
        sheet = cast(_Sheet, sheets.getByName(sheet_name))
        chart_names = set(sheet.getCharts().getElementNames())
        draw_page = sheet.getDrawPage()
        items: list[dict[str, object]] = []
        for index in range(draw_page.getCount()):
            shape = draw_page.getByIndex(index)
            shape_type = _safe_attr(shape, "getShapeType")
            if shape_type != "com.sun.star.drawing.OLE2Shape":
                continue
            persist_name = _safe_attr(shape, "PersistName")
            if persist_name not in chart_names:
                continue
            position = _safe_attr(shape, "Position")
            size = _safe_attr(shape, "Size")
            items.append(
                {
                    "name": _safe_attr(shape, "Name") or persist_name or "Chart",
                    "persist_name": persist_name,
                    "left": _hmm_to_points(getattr(position, "X", None)),
                    "top": _hmm_to_points(getattr(position, "Y", None)),
                    "width": _hmm_to_points(getattr(size, "Width", None)),
                    "height": _hmm_to_points(getattr(size, "Height", None)),
                }
            )
        sheets_payload[str(sheet_name)] = items
    return {"sheets": sheets_payload}


def _extract_draw_page_payload(doc: _SpreadsheetDocument) -> dict[str, object]:
    sheets_payload: dict[str, list[dict[str, object]]] = {}
    sheets = doc.getSheets()
    for sheet_name in sheets.getElementNames():
        sheet = cast(_Sheet, sheets.getByName(sheet_name))
        draw_page = sheet.getDrawPage()
        items: list[dict[str, object]] = []
        for index in range(draw_page.getCount()):
            shape = draw_page.getByIndex(index)
            shape_type = _safe_attr(shape, "getShapeType")
            if shape_type == "com.sun.star.drawing.OLE2Shape":
                continue
            position = _safe_attr(shape, "Position")
            size = _safe_attr(shape, "Size")
            items.append(
                {
                    "name": _safe_attr(shape, "Name") or f"Shape {index + 1}",
                    "shape_type": shape_type,
                    "text": _safe_attr(shape, "String") or "",
                    "left": _hmm_to_points(getattr(position, "X", None)),
                    "top": _hmm_to_points(getattr(position, "Y", None)),
                    "width": _hmm_to_points(getattr(size, "Width", None)),
                    "height": _hmm_to_points(getattr(size, "Height", None)),
                    "rotation": _rotation_to_degrees(_safe_attr(shape, "RotateAngle")),
                    "is_connector": shape_type == "com.sun.star.drawing.ConnectorShape",
                    "start_shape_name": _safe_shape_name(shape, "StartShape"),
                    "end_shape_name": _safe_shape_name(shape, "EndShape"),
                }
            )
        sheets_payload[str(sheet_name)] = items
    return {"sheets": sheets_payload}


def _safe_attr(obj: object, name: str) -> object:
    if name == "getShapeType":
        try:
            return cast(_ShapeLike, obj).getShapeType()
        except Exception:  # noqa: BLE001
            return None
    try:
        return getattr(obj, name)
    except Exception:  # noqa: BLE001
        return None


def _close_document(doc: _SpreadsheetDocument) -> None:
    try:
        doc.close(True)
    except Exception:  # noqa: BLE001
        try:
            doc.dispose()
        except Exception:  # noqa: BLE001
            return


def _safe_shape_name(obj: object, attr_name: str) -> str | None:
    try:
        ref = getattr(obj, attr_name)
    except Exception:  # noqa: BLE001
        return None
    if ref is None:
        return None
    name = _safe_attr(ref, "Name")
    return name if isinstance(name, str) and name else None


def _hmm_to_points(value: object) -> int | None:
    if not isinstance(value, int | float):
        return None
    return int(round(float(value) / _HMM_PER_POINT))


def _rotation_to_degrees(value: object) -> float | None:
    if not isinstance(value, int | float):
        return None
    return float(value) / 100.0


if __name__ == "__main__":
    raise SystemExit(main())
