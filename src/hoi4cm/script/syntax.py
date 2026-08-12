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


# Clausewitz/Paradox script has no string escapes, so a backslash is a literal
# character and a string closes at the very next quote. Treating ``\"`` as an
# escape swallows the closing quote of values that end in a backslash (e.g.
# ``icon = "gfx\interface\"``) and derails the rest of the parse. Every quoted
# alternative below is therefore ``"[^"]*"?`` — greedy to the next quote, with
# the closer optional so an unterminated string runs to the end of its scope
# instead of failing the match.
_QUOTED = r'"[^"]*"?'

# The scanners are compiled alternations rather than per-character Python
# loops: at the reference mod's scale (1.05M lines, 23.5k focus blocks) the
# per-character form dominated cold-load CPU, and the GIL rules out
# parallelising it away. Every alternative consumes its whole construct, so
# ``finditer`` skips strings and comments for us instead of us repositioning
# an index by hand.
# Comments are the one alternative left outside the capture group, so
# ``findall`` reports them as "" and every real token comes back non-empty —
# which lets the whole scan run as one C-level ``findall`` instead of a Python
# loop over match objects.
_TOKEN_RE = re.compile(rf'#[^\n]*|({_QUOTED}|[{{}}=]|[^ \t\n\r{{}}="#]+)')

# Group 1 keeps quoted strings verbatim; comments match outside it and, being
# an unmatched group in the ``\1`` template, substitute to nothing. Both
# alternatives stop at a newline: a comment ends with its line, and a string
# that never closes must not swallow the next line's comment.
_COMMENT_RE = re.compile(r'("[^"\n]*"?)|#[^\n]*')

_BRACE_RE = re.compile(rf"{_QUOTED}|#[^\n]*|[{{}}]")

# ``(?<!\w)`` replaces the old "is the previous character part of an
# identifier?" guard, so ``nested = {`` inside ``notnested = {`` still isn't a
# block start. A block-start match stops at its ``{`` and never swallows the
# body, so a nested block is found by the very next search.
_BLOCK_SCAN_RE = re.compile(
    rf"{_QUOTED}|#[^\n]*|(?<!\w)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{{"
)


def strip_comments(source: str) -> str:
    """Remove comments outside quoted strings while retaining line structure.

    Line endings are normalized to ``\\n`` first (``str.splitlines`` also
    breaks on ``\\v``, ``\\f`` and friends), so the substitution below can
    treat ``\\n`` as the only line break. Doing it in this order also keeps a
    line that was nothing but a comment as an empty line rather than deleting
    it, which downstream raw-block dedenting depends on.
    """
    return _COMMENT_RE.sub(r"\1", "\n".join(source.splitlines()))


def _unquote(token: str) -> str:
    """Return a captured ``"..."`` token without its quotes.

    The closing quote is optional in the pattern, so an unterminated string
    yields everything after the opening quote.
    """
    return token[1:-1] if len(token) > 1 and token[-1] == '"' else token[1:]


def tokenize(source: str) -> list[str]:
    """Split Paradox script into braces, equals signs, and value tokens."""
    parts = _TOKEN_RE.findall(source)
    if '"' not in source:
        # Nothing to unquote; only comments (captured as "") need dropping.
        return [text for text in parts if text] if "#" in source else parts
    return [_unquote(text) if text[0] == '"' else text for text in parts if text]


def parse_block(tokens: Sequence[str], position: int) -> tuple[dict[str, object], int]:
    """Parse a brace block, collecting duplicate keys into ordered lists."""
    result: dict[str, object] = {}
    value: object
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
    for match in _BRACE_RE.finditer(source, open_index):
        char = match.group()
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return match.start()
    return len(source)


def extract_block(source: str, open_index: int = 0) -> tuple[str, int]:
    """Return text inside a brace block and its close-brace index.

    An unbalanced block returns the remaining source and ``len(source) - 1``.
    """
    close_index = match_brace(source, open_index)
    if close_index >= len(source):
        return source[open_index + 1 :], max(len(source) - 1, open_index)
    return source[open_index + 1 : close_index], close_index


def _raw_start(source: str, position: int, name_start: int) -> int:
    """Return where a block's raw text begins: its leading whitespace run.

    ``_BLOCK_SCAN_RE`` anchors on the block name, but callers slice raw text
    from the earliest index the previous scan left off at, so back up over
    whitespace the way the old ``\\s*``-prefixed per-position match did.
    """
    start = name_start
    while start > position and source[start - 1].isspace():
        start -= 1
    return start


def find_blocks(source: str) -> list[tuple[str, str, str]]:
    """Return top-level ``(name, inner, raw)`` brace blocks in source order."""
    blocks: list[tuple[str, str, str]] = []
    position = 0
    while position < len(source):
        match = _BLOCK_SCAN_RE.search(source, position)
        if match is None:
            break
        name = match.group("name")
        if name is None:  # a quoted string or a comment — skip past it
            position = match.end()
            continue
        start = _raw_start(source, position, match.start("name"))
        inner, close_index = extract_block(source, match.end() - 1)
        blocks.append((name, inner, source[start : close_index + 1]))
        position = close_index + 1
    return blocks


def extract_named_block(source: str, name: str) -> str | None:
    """Return the untrimmed inner source of the first named brace block."""
    position = 0
    while position < len(source):
        match = _BLOCK_SCAN_RE.search(source, position)
        if match is None:
            break
        if match.group("name") == name:
            inner, _ = extract_block(source, match.end() - 1)
            return inner
        position = match.end()
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
