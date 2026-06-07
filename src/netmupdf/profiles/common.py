"""Shared helpers for device-specific profiles."""

from __future__ import annotations

import re

KNOWN_CHARACTER_REPLACEMENTS = str.maketrans(
    {
        "\uf06d": "-",
        "\uf073": "-",
        "\uf0b7": "-",
        "\uf0d8": "-",
        "\uf0fc": "-",
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
    }
)
PROMPT_PATTERN = re.compile(
    r"(?<!\S)(?P<prompt>>|#(?!#)|\([^)\r\n]+\)[#>])"
    r"(?=\S|[ \t]+\S|[ \t]*$)"
)


def heading_key(text: str) -> str:
    text = re.sub(r"^#{1,6}\s*", "", text.strip()).strip("` ")
    return re.sub(r"[\s\u3000]+", "", text)


def remove_duplicate_opening_headings(
    markdown: str, hierarchies: list[tuple[str, ...]]
) -> str:
    expected = {heading_key(title) for hierarchy in hierarchies for title in hierarchy}
    lines = markdown.lstrip().splitlines()
    position = 0
    while position < len(lines):
        line = lines[position]
        if not line.strip():
            position += 1
            continue
        if re.match(r"^#{1,6}\s+", line) and heading_key(line) in expected:
            position += 1
            continue
        break
    return "\n".join(lines[position:]).lstrip()


def unknown_character_warning(text: str, page_number: int) -> str | None:
    suspicious = sorted(
        {
            character
            for character in text
            if character == "\ufffd" or "\ue000" <= character <= "\uf8ff"
        },
        key=ord,
    )
    if not suspicious:
        return None
    descriptions = ", ".join(f"U+{ord(character):04X}" for character in suspicious)
    return f"ページ {page_number}: 未知の特殊文字を検出しました ({descriptions})"


def split_prompt_commands(line: str) -> list[str]:
    matches = list(PROMPT_PATTERN.finditer(line))
    if not matches:
        return [line]

    parts: list[str] = []
    prefix = line[: matches[0].start()].strip()
    if prefix:
        parts.append(prefix)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        parts.append(line[match.start() : end].strip())
    return parts


def is_prompt_line(line: str) -> bool:
    return bool(PROMPT_PATTERN.match(line.strip()))


def format_input_section(lines: list[str]) -> list[str]:
    content: list[str] = []
    for line in lines:
        line = line.rstrip()
        if line.strip() and not line.lstrip().startswith("no "):
            content.extend(re.split(r"\s+(?=no [a-zA-Z])", line))
        else:
            content.append(line)
    while content and not content[0].strip():
        content.pop(0)
    while content and not content[-1].strip():
        content.pop()
    if not content:
        return []

    result: list[str] = [""]
    code_buffer: list[str] = []

    def flush_code() -> None:
        while code_buffer and not code_buffer[0].strip():
            code_buffer.pop(0)
        while code_buffer and not code_buffer[-1].strip():
            code_buffer.pop()
        if not code_buffer:
            return
        result.extend(["```text", *code_buffer, "```", ""])
        code_buffer.clear()

    for line in content:
        stripped = line.strip()
        if stripped.startswith("<!-- PDF_PAGE:"):
            flush_code()
            result.extend([stripped, ""])
        else:
            code_buffer.append(line)
    flush_code()
    return result


def format_example_section(lines: list[str]) -> list[str]:
    expanded: list[str] = []
    for line in lines:
        expanded.extend(split_prompt_commands(line))

    result: list[str] = []
    terminal_buffer: list[str] = []
    in_terminal = False

    def flush_terminal() -> None:
        if not terminal_buffer:
            return
        result.extend(["```text", *terminal_buffer, "```", ""])
        terminal_buffer.clear()

    for line in expanded:
        stripped = line.strip()
        if stripped.startswith("<!-- PDF_PAGE:"):
            flush_terminal()
            result.extend([stripped, ""])
            continue
        if is_prompt_line(stripped):
            in_terminal = True
            terminal_buffer.append(stripped)
            if stripped in {"#", ">"}:
                flush_terminal()
                in_terminal = False
        elif re.match(r"^#{1,6}\s+\S", stripped):
            flush_terminal()
            in_terminal = False
            result.append(line.rstrip())
        elif in_terminal:
            if stripped:
                terminal_buffer.append(line.rstrip())
        else:
            result.append(line.rstrip())
    flush_terminal()
    return result


def format_code_sections(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    position = 0
    label_re = re.compile(r"^#### 【(.+)】\s*$")

    while position < len(lines):
        match = label_re.match(lines[position])
        if not match:
            output.append(lines[position])
            position += 1
            continue

        label = match.group(1)
        output.append(lines[position])
        position += 1
        content: list[str] = []
        while position < len(lines) and not label_re.match(lines[position]):
            content.append(lines[position])
            position += 1

        if label == "入力形式":
            output.extend(format_input_section(content))
        elif label == "実行例":
            output.extend(format_example_section(content))
        else:
            output.extend(content)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()
