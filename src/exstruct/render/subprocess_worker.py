from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RenderWorkerRequest:
    """Request payload for PDF page rendering worker."""

    pdf_path: Path
    output_dir: Path
    sheet_index: int
    safe_name: str
    dpi: int
    started_path: Path
    result_path: Path

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RenderWorkerRequest:
        """Build worker request from JSON payload."""
        return cls(
            pdf_path=Path(str(payload["pdf_path"])),
            output_dir=Path(str(payload["output_dir"])),
            sheet_index=int(payload["sheet_index"]),
            safe_name=str(payload["safe_name"]),
            dpi=int(payload["dpi"]),
            started_path=Path(str(payload["started_path"])),
            result_path=Path(str(payload["result_path"])),
        )


@dataclass(frozen=True)
class RenderWorkerResult:
    """Result payload emitted by render worker."""

    paths: list[str]
    error: str | None = None

    @classmethod
    def success(cls, paths: list[str]) -> RenderWorkerResult:
        """Build success result payload."""
        return cls(paths=paths, error=None)

    @classmethod
    def failure(cls, message: str) -> RenderWorkerResult:
        """Build failure result payload."""
        return cls(paths=[], error=message)

    def to_payload(self) -> dict[str, list[str] | str]:
        """Convert result model to JSON payload."""
        if self.error is not None:
            return {"error": self.error}
        return {"paths": self.paths}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse worker command line arguments."""
    parser = argparse.ArgumentParser(description="ExStruct render subprocess worker.")
    parser.add_argument(
        "--request-file",
        required=True,
        help="Path to worker request JSON file.",
    )
    return parser.parse_args(argv)


def _read_request(path: Path) -> RenderWorkerRequest:
    """Read and parse worker request file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request payload must be a JSON object.")
    return RenderWorkerRequest.from_payload(payload)


def _write_result(path: Path, result: RenderWorkerResult) -> None:
    """Write result JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(result.to_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _format_error(exc: Exception) -> str:
    """Format worker exception for parent process diagnostics."""
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__


def _render_pdf_pages(request: RenderWorkerRequest) -> list[str]:
    """Render all pages of one PDF to PNG files."""
    import pypdfium2 as pdfium

    scale = request.dpi / 72.0
    request.output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with pdfium.PdfDocument(str(request.pdf_path)) as pdf:
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
            page_suffix = f"_p{page_index + 1:02d}" if page_index > 0 else ""
            img_path = (
                request.output_dir
                / f"{request.sheet_index + 1:02d}_{request.safe_name}{page_suffix}.png"
            )
            pil_image.save(img_path, format="PNG", dpi=(request.dpi, request.dpi))
            written.append(str(img_path))
    return written


def main(argv: list[str] | None = None) -> int:
    """Run the render worker entrypoint."""
    request: RenderWorkerRequest | None = None
    try:
        args = _parse_args(argv)
        request = _read_request(Path(args.request_file))
        request.started_path.parent.mkdir(parents=True, exist_ok=True)
        request.started_path.write_text("started", encoding="utf-8")
        paths = _render_pdf_pages(request)
        _write_result(request.result_path, RenderWorkerResult.success(paths))
        return 0
    except Exception as exc:  # pragma: no cover - validated by parent-side tests
        if request is not None:
            _write_result(
                request.result_path, RenderWorkerResult.failure(_format_error(exc))
            )
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
