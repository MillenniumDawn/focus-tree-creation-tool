"""Pure sidebar-form snapshot helpers for Focus autosave.

Keeps the select-away dirty check off Tk widgets so it can be unit-tested.
A missed field here silently drops an edit on focus switch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from hoi4cm.script.syntax import parse_script

from .focus import Focus

_DEFAULT_GFX = "GFX_goal_generic_political_pressure"
_DEFAULT_SEARCH = "FOCUS_FILTER_POLITICAL"
_ID_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_]")


def form_focus_id(raw: str, current: str | None) -> str:
    """The focus id the sidebar writes for the name field's ``raw`` text.

    An untouched field keeps an imported id verbatim; sanitizing it would
    read the untouched form as a rename on every select-away.
    """
    if current is not None and raw == current:
        return raw
    return _ID_SANITIZE_RE.sub("_", raw)


def parse_ai_will_do(raw_ai: str) -> int:
    """Top-level numeric ai_will_do value from a raw block body.

    Reuses the import parser: a top-level ``factor`` wins over ``base``,
    duplicated keys parse as lists and, like any other non-numeric value,
    fall back to 1.
    """
    parsed = parse_script(raw_ai)
    value = parsed.get("factor", parsed.get("base", 1))
    if not isinstance(value, str | int | float):
        return 1
    try:
        return int(float(value))
    except ValueError, OverflowError:
        # OverflowError: infinite float tokens (inf, 1e999) are not int()-able.
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


def _shown_offsets(focus: Focus) -> tuple[dict[str, Any], ...]:
    """The offsets the sidebar shows for ``focus``, trigger text stripped."""
    return tuple(
        {**offset, "trigger": str(offset.get("trigger", "")).strip()}
        for offset in getattr(focus, "offsets", [])
    )


def sidebar_values_match_focus(focus: Focus, values: FocusSidebarValues) -> bool:
    """True when writing ``values`` onto ``focus`` would change nothing.

    Imported condition blocks, offset triggers and localisation text keep
    their surrounding whitespace, but the form reads every text widget back
    stripped. Compare them stripped so an untouched form never reads as an
    edit.
    """
    return (
        focus.name == values.name
        and focus.icon == values.icon
        and getattr(focus, "gfx", _DEFAULT_GFX) == values.gfx
        and focus.cost == values.cost
        and _ai_raw_text(focus) == values.ai_will_do_raw
        and focus.ai_will_do == values.ai_will_do
        and focus.x == values.x
        and focus.y == values.y
        and getattr(focus, "loc_name", "").strip() == values.loc_name
        and focus.desc.strip() == values.desc
        and getattr(focus, "search_filters", _DEFAULT_SEARCH) == values.search_filters
        and getattr(focus, "available_cond", "").strip() == values.available_cond
        and getattr(focus, "bypass_cond", "").strip() == values.bypass_cond
        and getattr(focus, "cancel_cond", "").strip() == values.cancel_cond
        and focus.cancel_if_invalid == values.cancel_if_invalid
        and focus.continue_if_invalid == values.continue_if_invalid
        and focus.available_if_capitulated == values.available_if_capitulated
        and _shown_offsets(focus) == values.offsets
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
