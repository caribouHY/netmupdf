# NetMuPDF

ネットワーク機器のPDFマニュアルを、CodexやClaudeが参照しやすいMarkdownファイルへ変換するツールです。
PDFのしおりを活用して、階層的なセクションごとにMarkdownを生成します。

## 特徴

- 指定したしおりレベルでMarkdownを分割
- 最初のしおりより前のページを `000_front_matter.md` に出力
- 元PDFのページ境界を `<!-- PDF_PAGE: 123 -->` として保持
- `index.md` と `toc_sections.csv` を自動生成
- 同じページを指す複数のしおりを1ファイルに集約
- PyMuPDF4LLMによる見出し・表・段組みの解析
- ページヘッダーとフッターの除去
- 機種別プロファイルによる入力形式と実行例の整形
- テキストを抽出できないページを警告として記録

OCRは行いません。画像だけで構成されたPDFには、事前にOCR処理が必要です。

## 使用方法

PyPIからインストールしてCLIを実行します。

```powershell
pip install netmupdf
netmupdf manuals\manual.pdf --level 2
```

開発中の作業ツリーから実行する場合:

```powershell
uv sync
uv run netmupdf manuals\manual.pdf --level 2
```

出力先を指定する場合:

```powershell
uv run netmupdf manuals\manual.pdf --out output\manual --level 2
```

分割予定だけを確認する場合:

```powershell
uv run netmupdf manuals\manual.pdf --level 2 --dry-run
```

空でない出力先へ書き込む場合:

```powershell
uv run netmupdf manuals\manual.pdf --out output\manual --force
```

変換中はセクション単位の進捗が表示されます。

```text
[  0%] 0/3 変換中: Part One / Introduction
[ 33%] 1/3 変換中: Part One / Configuration
[ 67%] 2/3 変換中: Appendix / Commands
[100%] 3/3 完了
```

### 後処理プロファイル

`--profile`オプションで、機種別の後処理プロファイルを指定できます。

- `fitelnet`: FITELnetコマンドリファレンス用 (F70コマンドリファレンス構成定義編/運用管理編で動作を確認しています。)
- `srs`: SR-Sシリーズコマンドリファレンス用 (SR-S V14コマンドリファレンスで動作を確認しています。)
- `generic`(default): 汎用的な後処理で、上記以外のPDFに適しています。

実行例:

```powershell
uv run netmupdf f70_cmd_ope_ref.pdf --profile fitelnet
uv run netmupdf sr_s_cmd.pdf --profile srs
```

## 出力

```text
manual_markdown/
├── 000_front_matter.md
├── 001_概要.md
├── 002_設定.md
├── index.md
└── toc_sections.csv
```

各Markdownには元PDF名、ページ範囲、しおり階層、ページ境界と抽出本文が
含まれます。`index.md` は全セクションへのリンク、`toc_sections.csv` は
ページ範囲や警告を含む機械可読の一覧です。

## 制限事項

- 入力は単一PDFのみです。
- PDFにしおりと抽出可能な文字情報が必要です。
- 複雑な表、段組み、図の配置は完全には再現されない場合があります。
- パスワード保護されたPDFは変換できません。

## テスト

```powershell
uv run pytest
uv run tox
```

## ビルド

```powershell
uv build
```

## 手動リリース

PyPIへの公開は手動で行います。公開前に検証を通してから配布物を作成します。

```powershell
uv sync --locked --group dev
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv build
uv run twine check dist/*
```

公開する場合はPyPIのAPIトークンを設定してからアップロードします。

```powershell
$env:UV_PUBLISH_TOKEN="pypi-..."
uv publish
```

一度公開したバージョン番号は再利用できません。次回以降の公開では
`pyproject.toml` の `version` を更新してから配布物を作成してください。

