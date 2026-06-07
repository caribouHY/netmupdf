from __future__ import annotations

import csv
from pathlib import Path

import pymupdf
import pytest

from netmupdf import (
    Bookmark,
    ConversionError,
    Section,
    build_sections,
    convert_pdf,
    safe_filename,
)
from netmupdf.cli import build_parser, main
from netmupdf.core import _extract_section
from netmupdf.profiles.common import format_code_sections
from netmupdf.profiles.fitelnet import FitelnetProfile
from netmupdf.profiles.generic import GenericProfile
from netmupdf.profiles.srs import SrsProfile


def make_pdf(
    path: Path,
    page_texts: list[str | None],
    toc: list[list] | None = None,
) -> Path:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text is not None:
            page.insert_text((72, 72), text)
    if toc:
        document.set_toc(toc)
    document.save(path)
    document.close()
    return path


def test_level_two_conversion_with_front_matter_and_same_page_bookmarks(
    tmp_path: Path,
) -> None:
    source = make_pdf(
        tmp_path / "日本語 manual.pdf",
        ["cover", "intro", "setup", "details", None],
        [
            [1, "Part One", 2],
            [2, "Introduction", 2],
            [2, "Quick Start", 2],
            [2, "Configuration", 3],
            [1, "Appendix", 5],
            [2, "Empty Page", 5],
        ],
    )
    output = tmp_path / "output"

    result = convert_pdf(source, output, level=2)

    assert [section.output_name for section in result.sections] == [
        "000_front_matter.md",
        "001_Introduction.md",
        "002_Configuration.md",
        "003_Empty_Page.md",
    ]
    assert result.warning_count == 1

    front_matter = (output / "000_front_matter.md").read_text(encoding="utf-8")
    introduction = (output / "001_Introduction.md").read_text(encoding="utf-8")
    final_section = (output / "003_Empty_Page.md").read_text(encoding="utf-8")
    assert "<!-- PDF_PAGE: 1 -->" in front_matter
    assert "# Part One" in introduction
    assert "## Introduction" in introduction
    assert "## Quick Start" in introduction
    assert introduction.count("<!-- PDF_PAGE: 2 -->") == 1
    assert "[!WARNING]" in final_section

    index = (output / "index.md").read_text(encoding="utf-8")
    assert "[Part One / Introduction](<001_Introduction.md>)" in index
    assert "PDF 5-5ページ / 警告: 1件" in index

    with (output / "toc_sections.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[2]["start_page"] == "3"
    assert rows[2]["end_page"] == "4"
    assert rows[3]["warning_count"] == "1"


def test_level_one_conversion_includes_last_page(tmp_path: Path) -> None:
    source = make_pdf(
        tmp_path / "manual.pdf",
        ["one", "two", "three"],
        [[1, "First", 1], [2, "Child", 2], [1, "Last", 3]],
    )

    result = convert_pdf(source, tmp_path / "out", level=1)

    assert [(item.start_page, item.end_page) for item in result.sections] == [
        (1, 2),
        (3, 3),
    ]
    last = (tmp_path / "out" / "002_Last.md").read_text(encoding="utf-8")
    assert "<!-- PDF_PAGE: 3 -->" in last
    assert "three" in last


def test_dry_run_does_not_create_output(tmp_path: Path) -> None:
    source = make_pdf(tmp_path / "manual.pdf", [None], [[1, "Chapter", 1]])
    output = tmp_path / "planned"

    result = convert_pdf(source, output, level=1, dry_run=True)

    assert result.dry_run is True
    assert result.warning_count == 1
    assert not output.exists()


def test_nonempty_output_requires_force(tmp_path: Path) -> None:
    source = make_pdf(tmp_path / "manual.pdf", ["text"], [[1, "Chapter", 1]])
    output = tmp_path / "out"
    output.mkdir()
    (output / "keep.txt").write_text("existing", encoding="utf-8")

    with pytest.raises(ConversionError, match="--force"):
        convert_pdf(source, output, level=1)

    convert_pdf(source, output, level=1, force=True)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "existing"
    assert (output / "001_Chapter.md").exists()


@pytest.mark.parametrize(
    ("toc", "level", "message"),
    [
        (None, 1, "しおりがありません"),
        ([[1, "Chapter", 1]], 2, "利用可能なレベル"),
    ],
)
def test_invalid_toc_errors(
    tmp_path: Path, toc: list[list] | None, level: int, message: str
) -> None:
    source = make_pdf(tmp_path / f"manual-{level}.pdf", ["text"], toc)

    with pytest.raises(ConversionError, match=message):
        convert_pdf(source, tmp_path / "out", level=level)


def test_cli_returns_nonzero_for_missing_pdf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(tmp_path / "missing.pdf")])

    assert exit_code == 1
    assert "エラー:" in capsys.readouterr().err


def test_safe_filename_handles_windows_characters_and_japanese() -> None:
    assert safe_filename(' 設定: "LAN/WAN"  ') == "設定_LAN_WAN"


def test_sections_are_stable_when_bookmarks_are_out_of_page_order() -> None:
    sections = build_sections(
        [
            Bookmark(1, "Later", 3, ("Later",)),
            Bookmark(1, "Earlier", 1, ("Earlier",)),
        ],
        page_count=4,
        target_level=1,
    )

    assert [(item.start_page, item.end_page) for item in sections] == [
        (1, 2),
        (3, 4),
    ]


def test_page_chunks_keep_order_markers_and_empty_page_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_pdf(
        tmp_path / "manual.pdf",
        ["first", None],
        [[1, "Chapter", 1]],
    )
    document = pymupdf.open(source)
    section = Section(
        index=1,
        titles=[("Chapter",)],
        start_page=1,
        end_page=2,
        output_name="001_Chapter.md",
    )
    monkeypatch.setattr(
        "netmupdf.core._extract_section_chunks",
        lambda _document, _section: [{"text": "page one"}, {"text": ""}],
    )

    markdown = _extract_section(document, section, source.name)
    document.close()

    assert markdown.index("<!-- PDF_PAGE: 1 -->") < markdown.index(
        "<!-- PDF_PAGE: 2 -->"
    )
    assert "page one" in markdown
    assert "ページ 2: テキストを抽出できませんでした" in markdown
    assert len(section.warnings) == 1


def test_postprocess_removes_only_duplicate_opening_headings() -> None:
    markdown, warning = FitelnetProfile().process_page(
        "## 第7 章 BGP の設定\n\n## 7.1 BGP の設定\n\n## 7.1.1 router bgp\n\n本文",
        255,
        [("第7章 BGPの設定", "7.1 BGPの設定")],
        remove_opening_headings=True,
    )

    assert warning is None
    assert "## 第7 章 BGP の設定" not in markdown
    assert "## 7.1 BGP の設定" not in markdown
    assert markdown.startswith("## 7.1.1 router bgp")


def test_postprocess_formats_input_and_example_commands() -> None:
    profile = FitelnetProfile()
    markdown, warning = profile.process_page(
        "【入力形式】 router bgp <AS番号> no router bgp <AS番号>\n\n"
        "【実行例】 BGPを設定します。\n\n"
        "#configure terminal (config)#router bgp 64496 "
        "(config-bgp)#",
        255,
        [("BGP",)],
        remove_opening_headings=False,
    )
    markdown = profile.process_section(markdown)

    assert warning is None
    assert "#### 【入力形式】\n\n```text" in markdown
    assert "router bgp <AS番号>\nno router bgp <AS番号>" in markdown
    assert "BGPを設定します。" in markdown
    assert (
        "```text\n#configure terminal\n(config)#router bgp 64496\n(config-bgp)#\n```"
    ) in markdown


def test_example_keeps_terminal_output_and_page_continuation_in_code() -> None:
    markdown = (
        "#### 【実行例】\n\n説明文です。\n\n"
        "#show interface\n"
        "Interface Status\n"
        "<!-- PDF_PAGE: 2 -->\n\n"
        "Loopback 0 up\n"
        "#\n\n"
        "後続の説明です。\n\n"
        "## 1.2 next command\n"
        "#### 【機能】\n\n次の機能"
    )

    formatted = format_code_sections(markdown)

    assert (
        "説明文です。\n\n```text\n#show interface\nInterface Status\n```" in formatted
    )
    assert "<!-- PDF_PAGE: 2 -->\n\n```text\nLoopback 0 up\n#\n```" in formatted
    assert "後続の説明です。" in formatted
    assert "```text\n後続の説明です。" not in formatted
    assert "## 1.2 next command" in formatted


def test_input_section_keeps_page_marker_outside_code() -> None:
    markdown = (
        "#### 【入力形式】\n\n"
        "show interface [detail]\n\n"
        "<!-- PDF_PAGE: 2 -->\n\n"
        "[verbose]\n\n"
        "#### 【動作モード】\n\nユーザモード"
    )

    formatted = format_code_sections(markdown)

    assert (
        "```text\nshow interface [detail]\n```\n\n"
        "<!-- PDF_PAGE: 2 -->\n\n"
        "```text\n[verbose]\n```"
    ) in formatted


def test_postprocess_normalizes_known_characters_and_warns_unknown() -> None:
    markdown, warning = FitelnetProfile().process_page(
        "\uf073 注意 ﬁle \ue123",
        10,
        [("Chapter",)],
        remove_opening_headings=False,
    )

    assert markdown == "- 注意 file \ue123"
    assert warning == "ページ 10: 未知の特殊文字を検出しました (U+E123)"


def test_index_link_handles_parentheses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_pdf(
        tmp_path / "manual.pdf",
        ["text"],
        [[1, "Address Pool (IPv4)", 1]],
    )
    monkeypatch.setattr(
        "netmupdf.core._extract_section_chunks",
        lambda _document, _section: [{"text": "text"}],
    )

    convert_pdf(source, tmp_path / "out", level=1)

    index = (tmp_path / "out" / "index.md").read_text(encoding="utf-8")
    assert "](<001_Address_Pool_(IPv4).md>)" in index


def test_generic_profile_preserves_extracted_markdown() -> None:
    source = "## `[入力形式]`\n\n```\nshow interface\n```"

    markdown, warning = GenericProfile().process_page(
        source,
        1,
        [("Chapter",)],
        remove_opening_headings=True,
    )

    assert warning is None
    assert markdown == source


def test_srs_profile_formats_labels_commands_and_models() -> None:
    profile = SrsProfile()
    source = (
        "## `1.1 command`\n\n"
        "## `[適用機種]`\n\n```\n"
        "SR-S752TR1SR-S748TC1\n```\n\n"
        "## `[入力形式]`\n\n```\ncommand <value>\n```\n\n"
        "## `[説明]`\n\n```\n説明文です。\n```"
    )

    markdown, warning = profile.process_page(
        source,
        1,
        [("Chapter",)],
        remove_opening_headings=False,
    )
    markdown = profile.process_section(markdown)

    assert warning is None
    assert "#### 【適用機種】" in markdown
    assert "SR-S752TR1\nSR-S748TC1" in markdown
    assert "#### 【入力形式】\n\n```text\ncommand <value>\n```" in markdown
    assert "#### 【説明】\n\n説明文です。" in markdown


def test_srs_example_with_spaced_prompt_is_one_code_block() -> None:
    profile = SrsProfile()
    source = (
        "## `[実行例]`\n\n"
        "# show candidate-config lan 0\n"
        "ip address 192.168.0.1/24 3\n"
        "ip rip use v1 v1 0 off\n"
        "#"
    )

    markdown, warning = profile.process_page(
        source,
        1,
        [("Chapter",)],
        remove_opening_headings=False,
    )
    markdown = profile.process_section(markdown)

    assert warning is None
    assert (
        "#### 【実行例】\n\n"
        "```text\n"
        "# show candidate-config lan 0\n"
        "ip address 192.168.0.1/24 3\n"
        "ip rip use v1 v1 0 off\n"
        "#\n"
        "```"
    ) in markdown


def test_empty_markdown_uses_standard_text_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_pdf(
        tmp_path / "manual.pdf",
        ["fallback command"],
        [[1, "Chapter", 1]],
    )
    document = pymupdf.open(source)
    section = Section(
        index=1,
        titles=[("Chapter",)],
        start_page=1,
        end_page=1,
        output_name="001_Chapter.md",
    )
    monkeypatch.setattr(
        "netmupdf.core._extract_section_chunks",
        lambda _document, _section: [{"text": ""}],
    )

    markdown = _extract_section(document, section, source.name)
    document.close()

    assert "fallback command" in markdown
    assert "[!WARNING]" not in markdown
    assert any("標準テキスト抽出を使用しました" in item for item in section.warnings)


def test_removed_duplicate_heading_is_not_reported_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_pdf(
        tmp_path / "manual.pdf",
        ["Chapter"],
        [[1, "Chapter", 1]],
    )
    document = pymupdf.open(source)
    section = Section(
        index=1,
        titles=[("Chapter",)],
        start_page=1,
        end_page=1,
        output_name="001_Chapter.md",
    )
    monkeypatch.setattr(
        "netmupdf.core._extract_section_chunks",
        lambda _document, _section: [{"text": "## Chapter"}],
    )

    markdown = _extract_section(document, section, source.name, profile="fitelnet")
    document.close()

    assert "<!-- PDF_PAGE: 1 -->" in markdown
    assert "[!WARNING]" not in markdown
    assert section.warnings == []


def test_srs_profile_removes_standard_extraction_footer() -> None:
    markdown, warning = SrsProfile().process_page(
        "ospf ip definfo off\n\n       第12 章 ルーティングプロトコル情報の設定   421",
        421,
        [("Chapter",)],
        remove_opening_headings=False,
    )

    assert warning is None
    assert markdown == "ospf ip definfo off"


def test_convert_pdf_rejects_unknown_profile(tmp_path: Path) -> None:
    source = make_pdf(
        tmp_path / "manual.pdf",
        ["text"],
        [[1, "Chapter", 1]],
    )

    with pytest.raises(ConversionError, match="未知のプロファイル"):
        convert_pdf(source, tmp_path / "out", level=1, profile="unknown")


def test_cli_profile_defaults_to_generic_and_rejects_unknown() -> None:
    parser = build_parser()

    assert parser.parse_args(["manual.pdf"]).profile == "generic"
    with pytest.raises(SystemExit):
        parser.parse_args(["manual.pdf", "--profile", "unknown"])
