"""Fujitsu SR-S manual Markdown post-processing."""

from __future__ import annotations

import re

from .common import (
    KNOWN_CHARACTER_REPLACEMENTS,
    format_code_sections,
    remove_duplicate_opening_headings,
    unknown_character_warning,
)

SECTION_LABELS = (
    "機能",
    "適用機種",
    "入力形式",
    "オプション",
    "動作モード",
    "説明",
    "注意",
    "実行例",
    "未設定時",
    "メッセージ",
    "初期値",
)
LABEL_PATTERN = "|".join(re.escape(label) for label in SECTION_LABELS)
LABEL_HEADING_RE = re.compile(rf"^##\s+`?\[({LABEL_PATTERN})\]`?\s*$", re.MULTILINE)
BARE_LABEL_RE = re.compile(rf"^\[({LABEL_PATTERN})\]\s*$", re.MULTILINE)


def _normalize_labels(markdown: str) -> str:
    markdown = LABEL_HEADING_RE.sub(
        lambda match: f"#### 【{match.group(1)}】", markdown
    )
    markdown = BARE_LABEL_RE.sub(lambda match: f"#### 【{match.group(1)}】", markdown)
    return markdown


def _unwrap_plain_code_blocks(markdown: str) -> str:
    return re.sub(r"^```\s*$", "", markdown, flags=re.MULTILINE)


def _separate_supported_models(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    in_models = False
    for line in lines:
        if line == "#### 【適用機種】":
            in_models = True
            output.append(line)
            continue
        if line.startswith("#### 【") or re.match(r"^##\s+", line):
            in_models = False
        if in_models and "SR-S" in line:
            line = re.sub(r"(?<!^)(?=SR-S)", "\n", line)
        output.append(line)
    return "\n".join(output)


def _remove_page_footer(markdown: str, page_number: int) -> str:
    return re.sub(
        rf"^[ \t]*第\d+\s*章[^\n]*[ \t]+{page_number}\s*$",
        "",
        markdown,
        flags=re.MULTILINE,
    )


class SrsProfile:
    name = "srs"

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
        markdown = _remove_page_footer(markdown, page_number)
        markdown = _unwrap_plain_code_blocks(markdown)
        markdown = _normalize_labels(markdown)
        markdown = _separate_supported_models(markdown)
        if remove_opening_headings:
            markdown = remove_duplicate_opening_headings(markdown, hierarchies)
        return re.sub(r"\n{3,}", "\n\n", markdown).strip(), warning

    def process_section(self, markdown: str) -> str:
        markdown = re.sub(
            r"^(#### 【[^】]+】)\n(?!\n)",
            r"\1\n\n",
            markdown,
            flags=re.MULTILINE,
        )
        return format_code_sections(markdown)
