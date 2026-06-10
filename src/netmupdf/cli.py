"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from .core import ConversionError, ConversionProgress, convert_pdf
from .profiles import PROFILE_NAMES


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1以上を指定してください")
    return parsed


class _ProgressReporter:
    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self.is_tty = stream.isatty()
        self.previous_width = 0

    def __call__(self, progress: ConversionProgress) -> None:
        percentage = (
            round(progress.completed / progress.total * 100) if progress.total else 100
        )
        if progress.current_section is None:
            status = "完了"
        else:
            status = f"変換中: {progress.current_section.display_title}"
        message = f"[{percentage:3d}%] {progress.completed}/{progress.total} {status}"

        if self.is_tty:
            padded_message = message.ljust(self.previous_width)
            self.stream.write(f"\r{padded_message}")
            self.stream.flush()
            self.previous_width = len(message)
            if progress.current_section is None:
                self.stream.write("\n")
                self.stream.flush()
        else:
            print(message, file=self.stream, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("PDFを指定したしおりレベルで分割し、AI向けMarkdownへ変換します。")
    )
    parser.add_argument("pdf", type=Path, help="入力PDF")
    parser.add_argument(
        "--out",
        type=Path,
        help="出力ディレクトリ（既定: <PDF名>_markdown）",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=2,
        help="分割に使うしおりレベル（既定: 2）",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="generic",
        help="後処理プロファイル（既定: generic）",
    )
    parser.add_argument(
        "--jobs",
        type=_positive_int,
        help="並列処理数（既定: CPU数に応じて自動、最大4）",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="速度を優先する旧Markdown抽出器を使用します",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="空でない出力ディレクトリへの書き込みを許可します",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ファイルを書き込まず分割予定を表示します",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    progress_reporter = _ProgressReporter(sys.stderr)
    try:
        result = convert_pdf(
            args.pdf,
            args.out,
            level=args.level,
            force=args.force,
            dry_run=args.dry_run,
            profile=args.profile,
            jobs=args.jobs,
            legacy=args.legacy,
            progress_callback=None if args.dry_run else progress_reporter,
        )
    except ConversionError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    if result.dry_run:
        print(f"出力予定: {result.output_dir}")
        for section in result.sections:
            warning = f" / 警告: {len(section.warnings)}件" if section.warnings else ""
            print(
                f"{section.output_name}: "
                f"PDF {section.start_page}-{section.end_page}ページ "
                f"({section.display_title}{warning})"
            )
        print(
            f"dry-run: {len(result.sections)}セクション、"
            f"警告 {result.warning_count}件（ファイル未作成）"
        )
        return 0

    print(f"完了: {len(result.sections)}セクション")
    print(f"出力先: {result.output_dir}")
    print(f"警告: {result.warning_count}件")
    return 0
