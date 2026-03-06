"""Validation helpers for LibreOffice-specific extraction constraints."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .errors import ConfigError

ExtractionMode = Literal["light", "libreoffice", "standard", "verbose"]

_LIBREOFFICE_XLS_MESSAGE = (
    ".xls is not supported in libreoffice mode; use COM-backed "
    "standard/verbose or convert to .xlsx"
)
_LIBREOFFICE_RENDER_MESSAGE = (
    "libreoffice mode does not support PDF/PNG rendering; "
    "use standard/verbose with Excel COM."
)
_LIBREOFFICE_AUTO_PAGE_BREAK_MESSAGE = (
    "libreoffice mode does not support auto page-break export; "
    "use standard/verbose with Excel COM."
)
_LIBREOFFICE_RENDER_AND_AUTO_PAGE_BREAK_MESSAGE = (
    "libreoffice mode does not support PDF/PNG rendering or auto page-break "
    "export; use standard/verbose with Excel COM."
)


def normalize_path(path: str | Path) -> Path:
    """Normalize a path-like input to ``Path``."""

    return path if isinstance(path, Path) else Path(path)


def _validate_libreoffice_file_path(
    file_path: str | Path,
    *,
    mode: ExtractionMode,
) -> Path:
    """Validate file-level constraints shared by LibreOffice-mode validators."""

    normalized_file_path = normalize_path(file_path)
    if mode != "libreoffice":
        return normalized_file_path
    if normalized_file_path.suffix.lower() == ".xls":
        raise ValueError(_LIBREOFFICE_XLS_MESSAGE)
    return normalized_file_path


def validate_libreoffice_extraction_request(
    file_path: str | Path,
    *,
    mode: ExtractionMode,
    include_auto_page_breaks: bool = False,
) -> Path:
    """Validate extraction-time constraints for LibreOffice mode."""

    normalized_file_path = _validate_libreoffice_file_path(file_path, mode=mode)
    if mode != "libreoffice":
        return normalized_file_path
    if include_auto_page_breaks:
        raise ConfigError(_LIBREOFFICE_AUTO_PAGE_BREAK_MESSAGE)
    return normalized_file_path


def validate_libreoffice_process_request(
    file_path: str | Path,
    *,
    mode: ExtractionMode,
    include_auto_page_breaks: bool = False,
    pdf: bool = False,
    image: bool = False,
) -> Path:
    """Validate process-time constraints for LibreOffice mode."""

    normalized_file_path = _validate_libreoffice_file_path(file_path, mode=mode)
    if mode != "libreoffice":
        return normalized_file_path
    render_requested = pdf or image
    if render_requested and include_auto_page_breaks:
        raise ConfigError(_LIBREOFFICE_RENDER_AND_AUTO_PAGE_BREAK_MESSAGE)
    if render_requested:
        raise ConfigError(_LIBREOFFICE_RENDER_MESSAGE)
    if include_auto_page_breaks:
        raise ConfigError(_LIBREOFFICE_AUTO_PAGE_BREAK_MESSAGE)
    return normalized_file_path
