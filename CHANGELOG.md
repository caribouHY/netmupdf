# Changelog

## [Unreleased]

### Added

- CLIで変換済みセクション数、割合、処理中セクション名を表示する進捗表示
- CLIの`--jobs`オプションと`convert_pdf()`の`jobs`引数による並列数指定

### Changed

- PDFセクション抽出をCPU数に応じて自動並列化し、ワーカー障害時は直列処理へフォールバック

## [0.1.0] - 2026-06-08

初版
