"""Tests for LibreOffice-specific request validation constraints."""

from pathlib import Path

import pytest

from exstruct import ConfigError
from exstruct.constraints import validate_libreoffice_process_request


def test_validate_libreoffice_process_request_rejects_auto_page_breaks_only() -> None:
    """Verify that validate LibreOffice process request rejects auto page breaks only."""

    with pytest.raises(ConfigError, match="does not support auto page-break export"):
        validate_libreoffice_process_request(
            Path("book.xlsx"),
            mode="libreoffice",
            include_auto_page_breaks=True,
        )


def test_validate_libreoffice_process_request_prefers_combined_error() -> None:
    """Verify that validate LibreOffice process request prefers combined error."""

    with pytest.raises(
        ConfigError,
        match="does not support PDF/PNG rendering or auto page-break export",
    ):
        validate_libreoffice_process_request(
            Path("book.xlsx"),
            mode="libreoffice",
            include_auto_page_breaks=True,
            pdf=True,
        )
