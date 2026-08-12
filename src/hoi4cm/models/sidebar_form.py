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
_AI_BASE_RE = re.compile(r"^\s*base\s*=\s*([\d.]+)", re.MULTILINE)
_AI_FACTOR_RE = re.compile(r"^\s*factor\s*=\s*([\d.]+)", re.MULTILINE)


def parse_ai_will_do(raw_ai: str) -> int:
    """Top-level numeric ai_will_do value from a raw block body.

    Accepts either ``base`` (MD top-level) or ``factor`` (modifier blocks).
    """
    match = _AI_BASE_RE.search(raw_ai) or _AI_FACTOR_RE.search(raw_ai)
    return int(float(match.group(1))) if match else 1


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
    desc: str
    search_filters: str
    available_cond: str
    bypass_cond: str
    cancel_cond: str
    cancel_if_invalid: bool
    continue_if_invalid: bool
    available_if_capitulated: bool
    offsets: tuple[dict[str, Any], ...]


def sidebar_values_match_focus(focus: Focus, values: FocusSidebarValues) -> bool:
    """True when writing ``values`` onto ``focus`` would change nothing."""
    return (
        focus.name == values.name
        and focus.icon == values.icon
        and getattr(focus, "gfx", _DEFAULT_GFX) == values.gfx
        and focus.cost == values.cost
        and getattr(focus, "ai_will_do_raw", "").strip() == values.ai_will_do_raw
        and focus.ai_will_do == values.ai_will_do
        and focus.x == values.x
        and focus.y == values.y
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
    Position is left to ``FocusDocument.move``.
    """
    name_changed = focus.name != values.name
    focus.name = values.name
    focus.icon = values.icon
    focus.gfx = values.gfx
    focus.cost = values.cost
    focus.ai_will_do_raw = values.ai_will_do_raw
    focus.ai_will_do = values.ai_will_do
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
