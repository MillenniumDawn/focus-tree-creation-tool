"""Low-level parsing and serialization for Paradox script syntax."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

__all__ = [
    "extract_block",
    "extract_named_block",
    "find_blocks",
    "match_brace",
    "parse_block",
    "parse_script",
    "serialize_block",
    "strip_comments",
    "tokenize",
]


_BLOCK_START_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{")


def _quoted_end(source: str, start: int) -> int:
    """Return the index past the closing quote.

    Clausewitz/Paradox script has no string escapes, so a backslash is a
    literal character and the string closes at the very next quote. Treating
    ``\\"`` as an escape swallows the closing quote of values that end in a
    backslash (e.g. ``icon = "gfx\\interface\\"``) and derails the rest of
    the parse.
    """
    position = source.find('"', start + 1)
    return position + 1 if position != -1 else len(source)


def strip_comments(source: str) -> str:
    """Remove comments outside quoted strings while retaining line structure."""
    lines: list[str] = []
    for line in source.splitlines():
        position = 0
        while position < len(line):
            if line[position] == '"':
                position = _quoted_end(line, position)
            elif line[position] == "#":
                line = line[:position]
                break
            else:
                position += 1
        lines.append(line)
    return "\n".join(lines)


def tokenize(source: str) -> list[str]:
    """Split Paradox script into braces, equals signs, and value tokens."""
    tokens: list[str] = []
    position = 0
    while position < len(source):
        char = source[position]
        if char in " \t\n\r":
            position += 1
        elif char in "{}=":
            tokens.append(char)
            position += 1
        elif char == "#":
            newline = source.find("\n", position)
            position = len(source) if newline < 0 else newline + 1
        elif char == '"':
            end = _quoted_end(source, position)
            closing_quote = (
                end <= len(source) and end > position and source[end - 1] == '"'
            )
            value_end = end - 1 if closing_quote else end
            tokens.append(source[position + 1 : value_end])
            position = end
        else:
            end = position
            while end < len(source) and source[end] not in ' \t\n\r{}="#':
                end += 1
            if end > position:
                tokens.append(source[position:end])
            position = end
    return tokens


def parse_block(tokens: Sequence[str], position: int) -> tuple[dict[str, object], int]:
    """Parse a brace block, collecting duplicate keys into ordered lists."""
    result: dict[str, object] = {}
    position += 1
    while position < len(tokens) and tokens[position] != "}":
        key = tokens[position]
        position += 1
        if position >= len(tokens):
            break
        if tokens[position] == "=":
            position += 1
            if position >= len(tokens):
                break
            if tokens[position] == "{":
                value, position = parse_block(tokens, position)
            else:
                value = tokens[position]
                position += 1
            if key in result:
                existing = result[key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    result[key] = [existing, value]
            else:
                result[key] = value
        elif key not in ("", "=", "{", "}"):
            values = result.setdefault("_values", [])
            if isinstance(values, list):
                values.append(key)
    return result, position + 1


def parse_script(source: str) -> dict[str, object]:
    """Parse a complete script as an implicit outer brace block."""
    tokens = ["{", *tokenize(source), "}"]
    result, _ = parse_block(tokens, 0)
    return result


def match_brace(source: str, open_index: int) -> int:
    """Return a matching close-brace index, or ``len(source)`` if missing."""
    depth = 0
    position = open_index
    while position < len(source):
        char = source[position]
        if char == '"':
            position = _quoted_end(source, position)
            continue
        if char == "#":
            newline = source.find("\n", position)
            if newline < 0:
                return len(source)
            position = newline + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return position
        position += 1
    return len(source)


def extract_block(source: str, open_index: int = 0) -> tuple[str, int]:
    """Return text inside a brace block and its close-brace index.

    An unbalanced block returns the remaining source and ``len(source) - 1``.
    """
    close_index = match_brace(source, open_index)
    if close_index >= len(source):
        return source[open_index + 1 :], max(len(source) - 1, open_index)
    return source[open_index + 1 : close_index], close_index


def _block_match(
    source: str, position: int, name: str | None = None
) -> re.Match[str] | None:
    match = _BLOCK_START_RE.match(source, position)
    if match is None:
        return None
    name_start = match.start(1)
    if (
        name_start > 0
        and name_start == position
        and (source[name_start - 1].isalnum() or source[name_start - 1] == "_")
    ):
        return None
    if name is not None and match.group(1) != name:
        return None
    return match


def find_blocks(source: str) -> list[tuple[str, str, str]]:
    """Return top-level ``(name, inner, raw)`` brace blocks in source order."""
    blocks: list[tuple[str, str, str]] = []
    position = 0
    while position < len(source):
        char = source[position]
        if char == '"':
            position = _quoted_end(source, position)
            continue
        if char == "#":
            newline = source.find("\n", position)
            position = len(source) if newline < 0 else newline
            continue
        match = _block_match(source, position)
        if match is None:
            position += 1
            continue
        open_index = match.end() - 1
        inner, close_index = extract_block(source, open_index)
        blocks.append((match.group(1), inner, source[position : close_index + 1]))
        position = close_index + 1
    return blocks


def extract_named_block(source: str, name: str) -> str | None:
    """Return the untrimmed inner source of the first named brace block."""
    position = 0
    while position < len(source):
        char = source[position]
        if char == '"':
            position = _quoted_end(source, position)
            continue
        if char == "#":
            newline = source.find("\n", position)
            position = len(source) if newline < 0 else newline + 1
            continue
        match = _block_match(source, position, name)
        if match is not None:
            inner, _ = extract_block(source, match.end() - 1)
            return inner
        position += 1
    return None


def _scalar_to_str(value: object, *, strip_strings: bool) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str) and strip_strings:
        return value.strip()
    return str(value)


def serialize_block(
    value: object,
    *,
    indent: str = "\t",
    include_bare_values: bool = False,
    strip_strings: bool = False,
) -> str:
    """Recursively serialize a parsed block without surrounding braces."""
    if not isinstance(value, Mapping):
        return _scalar_to_str(value, strip_strings=strip_strings)

    lines: list[str] = []
    for key, item in value.items():
        if str(key) == "_values" and include_bare_values:
            bare_values = item if isinstance(item, list) else [item]
            lines.extend(
                f"{indent}{_scalar_to_str(bare, strip_strings=strip_strings)}"
                for bare in bare_values
            )
            continue
        if str(key).startswith("_"):
            continue
        items = item if isinstance(item, list) else [item]
        for list_item in items:
            if isinstance(list_item, Mapping):
                inner = serialize_block(
                    list_item,
                    indent=indent + "\t",
                    include_bare_values=include_bare_values,
                    strip_strings=strip_strings,
                )
                lines.append(f"{indent}{key} = {{\n{inner}\n{indent}}}")
            else:
                rendered = _scalar_to_str(list_item, strip_strings=strip_strings)
                lines.append(f"{indent}{key} = {rendered}")
    return "\n".join(lines)
