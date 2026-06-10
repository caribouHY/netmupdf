"""Common PDF bookmark conversion pipeline."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import pymupdf4llm

from .profiles import ConversionProfile, get_profile


class ConversionError(Exception):
    """Raised when a PDF cannot be converted."""


@dataclass(frozen=True)
class Bookmark:
    level: int
    title: str
    page: int
    hierarchy: tuple[str, ...]


@dataclass
class Section:
    index: int
    titles: list[tuple[str, ...]]
    start_page: int
    end_page: int
    output_name: str
    warnings: list[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page + 1

    @property
    def display_title(self) -> str:
        return " / ".join(self.titles[0])


@dataclass(frozen=True)
class ConversionResult:
    sections: list[Section]
    warning_count: int
    output_dir: Path
    dry_run: bool


@dataclass(frozen=True)
class ConversionProgress:
    completed: int
    total: int
    current_section: Section | None


def safe_filename(text: str, max_len: int = 100) -> str:
    """Return a stable filename component that works on Windows."""
    text = re.sub(r'[\\/:*?"<>|]', "_", text.strip())
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.rstrip(". ")
    return text[:max_len].rstrip(". _") or "untitled"


def parse_bookmarks(toc: Iterable[list], target_level: int) -> list[Bookmark]:
    """Build target-level bookmarks with their parent hierarchy."""
    stack: list[str] = []
    bookmarks: list[Bookmark] = []

    for item in toc:
        level, title, page = int(item[0]), str(item[1]).strip(), int(item[2])
        if level < 1:
            continue

        stack = stack[: level - 1]
        while len(stack) < level - 1:
            stack.append("Untitled")
        stack.append(title or "Untitled")

        if level == target_level and page >= 1:
            bookmarks.append(
                Bookmark(
                    level=level,
                    title=title or "Untitled",
                    page=page,
                    hierarchy=tuple(stack),
                )
            )

    return bookmarks


def build_sections(
    bookmarks: list[Bookmark], page_count: int, target_level: int
) -> list[Section]:
    """Group same-page bookmarks and calculate inclusive page ranges."""
    if not bookmarks:
        raise ConversionError(f"しおりレベル {target_level} が見つかりません。")

    grouped: list[tuple[int, list[tuple[str, ...]]]] = []
    for bookmark in sorted(bookmarks, key=lambda item: item.page):
        page = min(bookmark.page, page_count)
        if grouped and grouped[-1][0] == page:
            grouped[-1][1].append(bookmark.hierarchy)
        else:
            grouped.append((page, [bookmark.hierarchy]))

    sections: list[Section] = []
    next_index = 1
    first_page = grouped[0][0]
    if first_page > 1:
        sections.append(
            Section(
                index=0,
                titles=[("Front Matter",)],
                start_page=1,
                end_page=first_page - 1,
                output_name="000_front_matter.md",
            )
        )

    for position, (start_page, titles) in enumerate(grouped):
        next_page = (
            grouped[position + 1][0] if position + 1 < len(grouped) else page_count + 1
        )
        end_page = next_page - 1
        if start_page > end_page:
            continue

        title = safe_filename(titles[0][-1])
        sections.append(
            Section(
                index=next_index,
                titles=titles,
                start_page=start_page,
                end_page=end_page,
                output_name=f"{next_index:03d}_{title}.md",
            )
        )
        next_index += 1

    return sections


def _heading_lines(hierarchies: list[tuple[str, ...]]) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for hierarchy in hierarchies:
        if hierarchy in seen:
            continue
        seen.add(hierarchy)
        for level, title in enumerate(hierarchy, start=1):
            heading = f"{'#' * min(level, 6)} {title}"
            if heading not in lines:
                lines.append(heading)
        lines.append("")
    return lines


def _extract_chunks(document: pymupdf.Document, page_indexes: list[int]) -> list[dict]:
    result = pymupdf4llm.to_markdown(
        document,
        pages=page_indexes,
        page_chunks=True,
        header=False,
        footer=False,
        use_ocr=False,
    )
    if not isinstance(result, list):
        raise RuntimeError("PyMuPDF4LLM returned an unexpected result")
    return result


def _extract_section_chunks(document: pymupdf.Document, section: Section) -> list[dict]:
    page_indexes = list(range(section.start_page - 1, section.end_page))
    try:
        chunks = _extract_chunks(document, page_indexes)
        if len(chunks) != len(page_indexes):
            raise RuntimeError(
                f"expected {len(page_indexes)} page chunks, got {len(chunks)}"
            )
        return chunks
    except Exception as section_error:
        chunks: list[dict] = []
        for page_index in page_indexes:
            page_number = page_index + 1
            try:
                page_chunks = _extract_chunks(document, [page_index])
                if len(page_chunks) != 1:
                    raise RuntimeError(f"expected 1 page chunk, got {len(page_chunks)}")
                chunks.append(page_chunks[0])
            except Exception as page_error:
                section.warnings.append(
                    f"ページ {page_number}: Markdown抽出に失敗しました ({page_error})"
                )
                chunks.append({"text": ""})
        section.warnings.append(
            "セクション一括抽出に失敗したためページ単位で再処理しました "
            f"({section_error})"
        )
        return chunks


def _extract_section(
    document: pymupdf.Document,
    section: Section,
    source_name: str,
    profile: ConversionProfile | str = "generic",
) -> str:
    if isinstance(profile, str):
        profile = get_profile(profile)
    quoted_source = json.dumps(source_name, ensure_ascii=False)
    lines = [
        "---",
        f"document: {quoted_source}",
        f"source_pdf: {quoted_source}",
        f'pages: "{section.start_page}-{section.end_page}"',
        "---",
        "",
        *_heading_lines(section.titles),
    ]

    chunks = _extract_section_chunks(document, section)
    content_lines: list[str] = []
    for offset, chunk in enumerate(chunks):
        page_number = section.start_page + offset
        raw_text = str(chunk.get("text", ""))
        source_had_text = bool(raw_text.strip())
        if not raw_text.strip():
            fallback_text = document.load_page(page_number - 1).get_text(
                "text", sort=True
            )
            if fallback_text.strip():
                raw_text = fallback_text
                source_had_text = True
                section.warnings.append(
                    f"ページ {page_number}: PyMuPDF4LLMの抽出結果が空のため"
                    "標準テキスト抽出を使用しました"
                )

        text, warning = profile.process_page(
            raw_text,
            page_number,
            section.titles,
            remove_opening_headings=offset == 0,
        )
        content_lines.extend([f"<!-- PDF_PAGE: {page_number} -->", ""])
        if warning:
            section.warnings.append(warning)
        if text:
            content_lines.extend([text, ""])
        elif not source_had_text:
            empty_warning = f"ページ {page_number}: テキストを抽出できませんでした"
            if not any(
                item.startswith(f"ページ {page_number}: Markdown抽出に失敗")
                for item in section.warnings
            ):
                section.warnings.append(empty_warning)
            content_lines.extend([f"> [!WARNING] {empty_warning}", ""])

    lines.extend([profile.process_section("\n".join(content_lines)), ""])
    return "\n".join(lines).rstrip() + "\n"


def _inspect_empty_pages(document: pymupdf.Document, sections: list[Section]) -> None:
    for section in sections:
        for page_number in range(section.start_page, section.end_page + 1):
            page = document.load_page(page_number - 1)
            if not page.get_text("text", sort=True).strip():
                section.warnings.append(
                    f"ページ {page_number}: テキストを抽出できませんでした"
                )


def _write_index(output_dir: Path, source_name: str, sections: list[Section]) -> None:
    lines = [
        f"# {Path(source_name).stem}",
        "",
        f"- 元PDF: `{source_name}`",
        f"- セクション数: {len(sections)}",
        "",
        "## セクション",
        "",
    ]
    for section in sections:
        warning = f" / 警告: {len(section.warnings)}件" if section.warnings else ""
        lines.append(
            f"- [{section.display_title}](<{section.output_name}>) "
            f"(PDF {section.start_page}-{section.end_page}ページ{warning})"
        )
    (output_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(output_dir: Path, sections: list[Section]) -> None:
    with (output_dir / "toc_sections.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "index",
                "title",
                "hierarchies",
                "start_page",
                "end_page",
                "page_count",
                "warning_count",
                "warnings",
                "output_markdown",
            ],
        )
        writer.writeheader()
        for section in sections:
            writer.writerow(
                {
                    "index": section.index,
                    "title": section.display_title,
                    "hierarchies": " | ".join(
                        " / ".join(item) for item in section.titles
                    ),
                    "start_page": section.start_page,
                    "end_page": section.end_page,
                    "page_count": section.page_count,
                    "warning_count": len(section.warnings),
                    "warnings": " | ".join(section.warnings),
                    "output_markdown": section.output_name,
                }
            )


def _prepare_output(output_dir: Path, force: bool) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        raise ConversionError(f"出力先がディレクトリではありません: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise ConversionError(
            f"出力先が空ではありません。上書きするには --force を指定してください: "
            f"{output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def convert_pdf(
    input_path: Path,
    output_dir: Path | None = None,
    *,
    level: int = 2,
    force: bool = False,
    dry_run: bool = False,
    profile: str = "generic",
    progress_callback: Callable[[ConversionProgress], None] | None = None,
) -> ConversionResult:
    """Convert one bookmarked PDF into sectioned Markdown files."""
    input_path = input_path.expanduser().resolve()
    if not input_path.is_file():
        raise ConversionError(f"PDFが見つかりません: {input_path}")
    if input_path.suffix.lower() != ".pdf":
        raise ConversionError(f"入力ファイルはPDFではありません: {input_path}")
    if level < 1:
        raise ConversionError("--level は1以上を指定してください。")
    try:
        selected_profile = get_profile(profile)
    except ValueError as exc:
        raise ConversionError(str(exc)) from exc

    output_dir = (
        output_dir.expanduser().resolve()
        if output_dir
        else input_path.with_name(f"{input_path.stem}_markdown")
    )

    try:
        document = pymupdf.open(input_path)
    except Exception as exc:
        raise ConversionError(f"PDFを開けません: {input_path}: {exc}") from exc

    try:
        if document.needs_pass:
            raise ConversionError(
                "暗号化されたPDFです。パスワード保護を解除してから実行してください。"
            )
        toc = document.get_toc()
        if not toc:
            raise ConversionError("このPDFにはしおりがありません。")

        available_levels = sorted({int(item[0]) for item in toc})
        bookmarks = parse_bookmarks(toc, level)
        if not bookmarks:
            raise ConversionError(
                f"しおりレベル {level} が見つかりません。"
                f"利用可能なレベル: {available_levels}"
            )
        sections = build_sections(bookmarks, document.page_count, level)

        if dry_run:
            _inspect_empty_pages(document, sections)
            return ConversionResult(
                sections=sections,
                warning_count=sum(len(section.warnings) for section in sections),
                output_dir=output_dir,
                dry_run=True,
            )

        _prepare_output(output_dir, force)
        if progress_callback is not None:
            progress_callback(
                ConversionProgress(
                    completed=0,
                    total=len(sections),
                    current_section=sections[0],
                )
            )
        for completed, section in enumerate(sections, start=1):
            markdown = _extract_section(
                document, section, input_path.name, selected_profile
            )
            (output_dir / section.output_name).write_text(markdown, encoding="utf-8")
            if progress_callback is not None:
                current_section = (
                    sections[completed] if completed < len(sections) else None
                )
                progress_callback(
                    ConversionProgress(
                        completed=completed,
                        total=len(sections),
                        current_section=current_section,
                    )
                )
        _write_index(output_dir, input_path.name, sections)
        _write_csv(output_dir, sections)
        return ConversionResult(
            sections=sections,
            warning_count=sum(len(section.warnings) for section in sections),
            output_dir=output_dir,
            dry_run=False,
        )
    finally:
        document.close()
