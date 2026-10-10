"""Ordered, tolerant codec for ``common/characters`` script files.

Unlike a dict-only parse, each assignment remains a separate ordered entry.
That matters for character files, where repeated role and portrait blocks are
valid and unknown fields must survive an edit/export cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from hoi4cm.script.syntax import emit_scalar

__all__ = [
    "CharacterScript",
    "ScriptBlock",
    "new_character_script",
    "parse_character_script",
    "serialize_character_script",
]

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


@dataclass
class ScriptBlock:
    """A script block as ordered key/value occurrences (including repeats)."""

    entries: list[tuple[str | None, str | ScriptBlock | _Comparison]] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class _Comparison:
    """An unkeyed comparison clause such as ``date >= 1936.1.1``."""

    left: str
    operator: str
    right: str


@dataclass(frozen=True)
class _ScriptToken:
    text: str
    quoted: bool = False
    operator: bool = False

    def is_punctuation(self, value: str) -> bool:
        return not self.quoted and self.text == value


_TOKEN_RE = re.compile(r'"[^\"]*"?|#[^\n]*|>=|<=|==|!=|[{}=<>!]|[^ \t\n\r{}="#<>!]+')


def _tokenize(source: str) -> list[_ScriptToken]:
    """Tokenize like the shared parser, retaining quotes and comparisons."""
    tokens: list[_ScriptToken] = []
    for match in _TOKEN_RE.finditer(source):
        text = match.group()
        if text.startswith("#"):
            continue
        if text.startswith('"'):
            value = text[1:-1] if text.endswith('"') else text[1:]
            tokens.append(_ScriptToken(value, quoted=True))
        elif text in (">=", "<=", "==", "!=", ">", "<", "!"):
            tokens.append(_ScriptToken(text, operator=True))
        else:
            tokens.append(_ScriptToken(text))

    merged: list[_ScriptToken] = []
    position = 0
    while position < len(tokens):
        token = tokens[position]
        merged.append(token)
        position += 1
    return merged


@dataclass
class CharacterScript:
    """Parsed character file, with helper access to its ``characters`` block."""

    root: ScriptBlock

    def character_ids(self) -> list[str]:
        result: list[str] = []
        for _, characters in self.root.entries:
            if _ != "characters" or not isinstance(characters, ScriptBlock):
                continue
            result.extend(
                key
                for key, _value in characters.entries
                if key is not None and isinstance(_value, ScriptBlock)
            )
        return result

    def to_text(self) -> str:
        return serialize_character_script(self)


class _Parser:
    def __init__(self, source: str) -> None:
        self.tokens = _tokenize(source)
        self.position = 0

    def block(self, *, nested: bool = False) -> ScriptBlock:
        if nested:
            if not self._take().is_punctuation("{"):
                raise ValueError("Expected a script block")
        result = ScriptBlock()
        while self.position < len(self.tokens):
            token = self._take()
            if token.is_punctuation("}"):
                if nested:
                    return result
                raise ValueError("Unexpected closing brace")
            if token.is_punctuation("{"):
                raise ValueError("Unexpected opening brace")
            result.entries.append(self._entry(token))
        if nested:
            raise ValueError("Unclosed script block")
        return result

    def _entry(
        self, token: _ScriptToken
    ) -> tuple[str | None, str | ScriptBlock | _Comparison]:
        if self.position < len(self.tokens) and self.tokens[self.position].operator:
            operator = self._take().text
            if self.position >= len(self.tokens):
                raise ValueError("Missing right operand for comparison")
            right = self._take()
            if not right.quoted and right.text in ("}", "=", "{"):
                raise ValueError("Invalid right operand for comparison")
            return None, _Comparison(token.text, operator, right.text)
        if self.position >= len(self.tokens) or not self.tokens[
            self.position
        ].is_punctuation("="):
            return None, token.text
        self.position += 1
        return token.text, self._assignment_value(token.text)

    def _assignment_value(self, key: str) -> str | ScriptBlock:
        if self.position >= len(self.tokens):
            raise ValueError(f"Missing value for {key!r}")
        if self.tokens[self.position].is_punctuation("{"):
            return self.block(nested=True)
        value = self._take()
        if not value.quoted and value.text in ("}", "=", "{"):
            raise ValueError(f"Invalid value for {key!r}")
        return value.text

    def _take(self) -> _ScriptToken:
        token = self.tokens[self.position]
        self.position += 1
        return token


def parse_character_script(source: str) -> CharacterScript:
    """Parse a file while retaining ordered duplicate assignments."""
    return CharacterScript(_Parser(source).block())


def _render(block: ScriptBlock, depth: int) -> str:
    indent = "\t" * depth
    lines: list[str] = []
    for key, value in block.entries:
        if key is None:
            if isinstance(value, _Comparison):
                lines.append(
                    f"{indent}{_emit_character_scalar(value.left)} "
                    f"{value.operator} {_emit_character_scalar(value.right)}"
                )
                continue
            if not isinstance(value, str):
                raise ValueError("Bare script values must be scalars")
            lines.append(f"{indent}{_emit_character_scalar(value)}")
        elif isinstance(value, ScriptBlock):
            rendered_key = _emit_character_scalar(key)
            lines.append(f"{indent}{rendered_key} = {{")
            inner = _render(value, depth + 1)
            if inner:
                lines.append(inner)
            lines.append(f"{indent}}}")
        elif isinstance(value, _Comparison):
            raise ValueError("Comparison clauses cannot have assignment keys")
        else:
            lines.append(
                f"{indent}{_emit_character_scalar(key)} = "
                f"{_emit_character_scalar(value)}"
            )
    return "\n".join(lines)


def _emit_character_scalar(value: str) -> str:
    """Quote scalars whose operator characters are syntax to this codec."""
    rendered = emit_scalar(value)
    if rendered.startswith('"') or not any(char in value for char in "<>!"):
        return rendered
    return f'"{rendered}"'


def serialize_character_script(document: CharacterScript) -> str:
    """Serialize a character file with repeated keys in their original order."""
    return _render(document.root, 0) + "\n"


def new_character_script(country_tag: str, character_id: str) -> str:
    """Return a minimal valid file for one new character."""
    if not _KEY_RE.fullmatch(country_tag) or not _KEY_RE.fullmatch(character_id):
        raise ValueError("Country tag and character ID must be script identifiers")
    return "characters = {\n" f"\t{character_id} = {{\n" '\t\tname = ""\n' "\t}\n" "}\n"
