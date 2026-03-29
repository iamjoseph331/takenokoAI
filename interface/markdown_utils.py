"""Shared markdown parsing utilities."""

from __future__ import annotations


def parse_markdown_sections(content: str) -> dict[str, str]:
    """Split markdown content by ``## `` headers into a ``{header: body}`` dict.

    Lines before the first ``## `` header are stored under the key ``"_preamble"``.
    """
    sections: dict[str, str] = {}
    current_header: str | None = None
    current_lines: list[str] = []

    for line in content.splitlines(keepends=True):
        if line.startswith("## "):
            if current_header is not None:
                sections[current_header] = "".join(current_lines)
            elif current_lines:
                # Text before the first header
                sections["_preamble"] = "".join(current_lines)
            current_header = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_header is not None:
        sections[current_header] = "".join(current_lines)
    elif current_lines:
        sections["_preamble"] = "".join(current_lines)

    return sections
