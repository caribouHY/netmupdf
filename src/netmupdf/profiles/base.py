"""Profile interface for device-specific Markdown post-processing."""

from __future__ import annotations

from typing import Protocol


class ConversionProfile(Protocol):
    name: str

    def process_page(
        self,
        markdown: str,
        page_number: int,
        hierarchies: list[tuple[str, ...]],
        *,
        remove_opening_headings: bool,
    ) -> tuple[str, str | None]: ...

    def process_section(self, markdown: str) -> str: ...
