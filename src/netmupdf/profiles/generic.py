"""Generic profile that preserves extracted Markdown."""

from __future__ import annotations

from .common import unknown_character_warning


class GenericProfile:
    name = "generic"

    def process_page(
        self,
        markdown: str,
        page_number: int,
        hierarchies: list[tuple[str, ...]],
        *,
        remove_opening_headings: bool,
    ) -> tuple[str, str | None]:
        del hierarchies, remove_opening_headings
        return markdown.strip(), unknown_character_warning(markdown, page_number)

    def process_section(self, markdown: str) -> str:
        return markdown.strip()
