"""Pure sidebar-form snapshot helpers for Focus autosave.

Keeps the select-away dirty check off Tk widgets so it can be unit-tested.
A missed field here silently drops an edit on focus switch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .focus import Focus

_DEFAULT_GFX = "GFX_goal_generic_political_pressure"
_DEFAULT_SEARCH = "FOCUS_FILTER_POLITICAL"
_ID_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_]")
_AI_ASSIGN_RE = re.compile(r"\s*=\s*")
# One scalar token, or a block opener (which the numeric parse then rejects).
_AI_TOKEN_RE = re.compile(r"[^{}\s}]+|\{")


def form_focus_id(raw: str, current: str | None) -> str:
    """The focus id the sidebar writes when the name field reads ``raw``.

    The field is repopulated verbatim from the focus, so an untouched form on
    an imported focus whose id contains characters a hand-typed id would not
    survive must read back unchanged rather than silently rename the focus to
    a sanitized id on every select-away. Editing the field triggers the usual
    sanitization.
    """
    if current is not None and raw == current:
        return raw
    return _ID_SANITIZE_RE.sub("_", raw)


def _top_level_assignment(raw_ai: str, key: str) -> str | None:
    """Token assigned to the first top-level ``key`` in an ai_will_do body.

    Reads the raw text the way ``build_focuses`` reads the parsed dict:
    comments and quoted strings are skipped, and a brace-depth count keeps
    keys nested inside modifier blocks from matching. An assignment whose
    value is itself a block returns its ``{`` opener, which the numeric
    parse then rejects, matching import's fallback to 1.
    """
    depth = 0
    length = len(raw_ai)
    index = 0
    while index < length:
        char = raw_ai[index]
        if char == '"':
            closing = raw_ai.find('"', index + 1)
            index = length if closing < 0 else closing + 1
            continue
        if char == "#":
            newline = raw_ai.find("\n", index)
            index = length if newline < 0 else newline + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and char == key[0] and raw_ai.startswith(key, index):
            word_end = index + len(key)
            previous = raw_ai[index - 1] if index else "\n"
            assignment = (
                _AI_ASSIGN_RE.match(raw_ai, word_end)
                if previous in "\t\n\r }"
                else None
            )
            if assignment is not None:
                token = _AI_TOKEN_RE.match(raw_ai, assignment.end())
                return token.group(0) if token else ""
            index = word_end
            continue
        index += 1
    return None


def parse_ai_will_do(raw_ai: str) -> int:
    """Top-level numeric ai_will_do value from a raw block body.

    Mirrors the import semantics in ``build_focuses``: a top-level ``factor``
    wins over ``base`` even when ``base`` appears first, keys nested in
    modifier blocks (or in comments/quoted strings) never count, and a value
    that does not parse as a number falls back to 1. Negative and fractional
    numbers survive the trip, which the previous digit-only regex dropped.
    """
    for key in ("factor", "base"):
        token = _top_level_assignment(raw_ai, key)
        if token is None:
            continue
        try:
            return int(float(token.strip('"')))
        except ValueError:
            return 1
    return 1


def parse_focus_cost(raw: str) -> int | float:
    """Parse a cost field, preserving fractional values from imported trees.

    ``build_focuses`` keeps non-integral costs as float (e.g. 7.5). The sidebar
    round-trips them via ``str(cost)``, so ``int(...)`` alone raises on select-away
    and forces a false dirty path / error log spam.
    """
    value = float(raw.strip())
    as_int = int(value)
    return as_int if value == as_int else value


@dataclass(frozen=True)
class FocusSidebarValues:
    name: str
    icon: str
    gfx: str
    cost: int | float
    ai_will_do: int
    ai_will_do_raw: str
    x: int
    y: int
    loc_name: str
    desc: str
    search_filters: str
    available_cond: str
    bypass_cond: str
    cancel_cond: str
    cancel_if_invalid: bool
    continue_if_invalid: bool
    available_if_capitulated: bool
    offsets: tuple[dict[str, Any], ...]


def _ai_raw_text(focus: Focus) -> str:
    """The ai_will_do text the sidebar shows for ``focus``."""
    # An empty raw block is shown as ``base = N``, so it must not read as dirty.
    raw = getattr(focus, "ai_will_do_raw", "").strip()
    return raw or f"base = {focus.ai_will_do}"


def sidebar_values_match_focus(focus: Focus, values: FocusSidebarValues) -> bool:
    """True when writing ``values`` onto ``focus`` would change nothing."""
    return (
        focus.name == values.name
        and focus.icon == values.icon
        and getattr(focus, "gfx", _DEFAULT_GFX) == values.gfx
        and focus.cost == values.cost
        and _ai_raw_text(focus) == values.ai_will_do_raw
        and focus.ai_will_do == values.ai_will_do
        and focus.x == values.x
        and focus.y == values.y
        and getattr(focus, "loc_name", "") == values.loc_name
        and focus.desc == values.desc
        and getattr(focus, "search_filters", _DEFAULT_SEARCH) == values.search_filters
        and getattr(focus, "available_cond", "") == values.available_cond
        and getattr(focus, "bypass_cond", "") == values.bypass_cond
        and getattr(focus, "cancel_cond", "") == values.cancel_cond
        and focus.cancel_if_invalid == values.cancel_if_invalid
        and focus.continue_if_invalid == values.continue_if_invalid
        and focus.available_if_capitulated == values.available_if_capitulated
        and tuple(getattr(focus, "offsets", [])) == values.offsets
    )


def apply_sidebar_values(focus: Focus, values: FocusSidebarValues) -> bool:
    """Write non-position form fields onto ``focus``.

    Returns True when ``name`` changed (caller must ``touch()`` name indexes).
    Position is left to ``FocusDocument.move``. When neither changes, the
    caller must still mark the content revision for other field edits.
    """
    name_changed = focus.name != values.name
    focus.name = values.name
    focus.icon = values.icon
    focus.gfx = values.gfx
    focus.cost = values.cost
    focus.ai_will_do_raw = values.ai_will_do_raw
    focus.ai_will_do = values.ai_will_do
    focus.loc_name = values.loc_name
    focus.desc = values.desc
    focus.search_filters = values.search_filters
    focus.available_cond = values.available_cond
    focus.bypass_cond = values.bypass_cond
    focus.cancel_cond = values.cancel_cond
    focus.cancel_if_invalid = values.cancel_if_invalid
    focus.continue_if_invalid = values.continue_if_invalid
    focus.available_if_capitulated = values.available_if_capitulated
    focus.offsets = [dict(offset) for offset in values.offsets]
    return name_changed
