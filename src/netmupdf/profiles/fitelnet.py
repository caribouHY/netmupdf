"""FITELnet manual Markdown post-processing."""

from __future__ import annotations

import re

from .common import (
    KNOWN_CHARACTER_REPLACEMENTS,
    format_code_sections,
    remove_duplicate_opening_headings,
    unknown_character_warning,
)

SECTION_LABELS = (
    "対応ファームウェアバージョン",
    "機能",
    "入力形式",
    "パラメータ",
    "パラメーター",
    "動作モード",
    "説明",
    "注意",
    "エラーメッセージ",
    "実行例",
    "各フィールドの意味",
    "未設定時",
)


def separate_section_labels(markdown: str) -> str:
    label_pattern = "|".join(re.escape(label) for label in SECTION_LABELS)
    markdown = re.sub(
        rf"\s*(#+\s*)?【({label_pattern})】\s*",
        lambda match: f"\n\n#### 【{match.group(2)}】\n\n",
        markdown,
    )
    return re.sub(r"\n{3,}", "\n\n", markdown).strip()


class FitelnetProfile:
    name = "fitelnet"

    def process_page(
        self,
        markdown: str,
        page_number: int,
        hierarchies: list[tuple[str, ...]],
        *,
        remove_opening_headings: bool,
    ) -> tuple[str, str | None]:
        markdown = markdown.translate(KNOWN_CHARACTER_REPLACEMENTS)
        warning = unknown_character_warning(markdown, page_number)
        markdown = separate_section_labels(markdown)
        if remove_opening_headings:
            markdown = remove_duplicate_opening_headings(markdown, hierarchies)
        return markdown.strip(), warning

    def process_section(self, markdown: str) -> str:
        return format_code_sections(markdown)
