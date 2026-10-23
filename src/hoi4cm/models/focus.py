"""Focus data model — the canvas item at the heart of every focus tree."""

import copy
import math
from collections.abc import Callable, Mapping

from .focus_icon import split_focus_icon

MAX_FOCUS_ID = 1_000_000


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except TypeError, ValueError, OverflowError:
        try:
            return int(float(value))
        except TypeError, ValueError, OverflowError:
            return default


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _as_int(value)


def _as_number(value: object, default: int | float = 10) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        number = float(value)
    except TypeError, ValueError, OverflowError:
        return default
    if not math.isfinite(number):
        return default
    if number.is_integer():
        try:
            return int(number)
        except TypeError, ValueError, OverflowError:
            return default
    return number


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, float) and math.isfinite(value):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _as_string(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return default


def _as_optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _as_string(value)


def _as_effects(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [copy.deepcopy(effect) for effect in value if isinstance(effect, dict)]


def _as_id_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [
        _as_int(item)
        for item in value
        if isinstance(item, (int, float, str)) and not isinstance(item, bool)
    ]


def _as_prereqs(value: object) -> list[list[int]]:
    if not isinstance(value, list):
        return []
    return [_as_id_list(group) for group in value if isinstance(group, list)]


def _as_name_groups(value: object) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    return [
        [item for item in group if isinstance(item, str)]
        for group in value
        if isinstance(group, list)
    ]


def _as_names(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str)]
        if isinstance(value, list)
        else []
    )


def _as_offsets(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    offsets = []
    for offset in value:
        if not isinstance(offset, dict):
            continue
        offsets.append(
            {
                "x": _as_int(offset.get("x")),
                "y": _as_int(offset.get("y")),
                "trigger": _as_string(offset.get("trigger")),
            }
        )
    return offsets


def _as_dict(value: object) -> dict[str, object] | None:
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _bounded_id(value: object) -> int:
    # Reject rather than merge distinct IDs or leave references pointing at old IDs.
    focus_id = _as_int(value, 1)
    if not 0 <= focus_id <= MAX_FOCUS_ID:
        raise ValueError(f"focus id must be between 0 and {MAX_FOCUS_ID}")
    return focus_id


_FIELD_COERCERS: dict[str, Callable[[object], object]] = {
    "id": _bounded_id,
    "name": _as_string,
    "loc_name": _as_string,
    "icon": _as_string,
    "gfx": lambda value: (
        value if isinstance(value, (dict, list)) else _as_string(value)
    ),
    "x": _as_int,
    "y": _as_int,
    "cost": _as_number,
    "desc": _as_string,
    "effects": _as_effects,
    "prereqs": _as_prereqs,
    "mutex": _as_id_list,
    "cancel_if_invalid": _as_bool,
    "continue_if_invalid": _as_bool,
    "available_if_capitulated": _as_bool,
    "ai_will_do": _as_int,
    "ai_will_do_raw": _as_string,
    "relative_position_id": _as_optional_string,
    "search_filters": _as_string,
    "available_cond": _as_string,
    "bypass_cond": _as_string,
    "cancel_cond": _as_string,
    "will_lead_to_war_with": _as_string,
    "complete_tooltip": _as_string,
    "select_effect": _as_string,
    "bypass_effect": _as_string,
    "allow_branch": _as_string,
    "text": _as_string,
    "offsets": _as_offsets,
    "tree_idx": _as_int,
    "_raw_gx": _as_optional_int,
    "_raw_gy": _as_optional_int,
    "_rel_dx": _as_optional_int,
    "_rel_dy": _as_optional_int,
    "_joint_extra": _as_string,
    "_script_extras": _as_dict,
    "_unresolved_prereqs": _as_name_groups,
    "_unresolved_mutex": _as_names,
    "_build_gx": _as_optional_int,
    "_build_gy": _as_optional_int,
    "_relative_pending": _as_bool,
}


class Focus:
    """A single national focus in the editor canvas."""

    # Set only when a focus is built from a parsed file; used to preserve the
    # original coordinates across edits. Declared here (no default) so mypy
    # knows they exist while `hasattr` still reports them absent on fresh
    # focuses.
    _raw_gx: int | None
    _raw_gy: int | None
    _rel_dx: int | None
    _rel_dy: int | None
    _joint_extra: str
    _script_extras: dict[str, object] | None
    _unresolved_prereqs: list[list[str]]
    _unresolved_mutex: list[str]
    _build_gx: int | None
    _build_gy: int | None
    _relative_pending: bool

    def __init__(self, *, id: int, x=0, y=0):  # pylint: disable=redefined-builtin
        self.id = _bounded_id(id)
        self.name = f"focus_{self.id}"
        self.loc_name = ""
        self.icon = "⚔"
        self.gfx = "GFX_goal_generic_political_pressure"
        self.x = x
        self.y = y
        self.cost: int | float = 10
        self.desc = ""
        self.effects: list[dict[str, object]] = []  # type + effect-specific fields
        self.prereqs: list[list[int]] = []  # AND of OR-groups
        self.mutex: list[int] = []
        self.cancel_if_invalid = True
        self.continue_if_invalid = False
        self.available_if_capitulated = False
        self.ai_will_do = 1
        self.ai_will_do_raw = ""  # full raw ai_will_do block if imported
        self.relative_position_id: str | None = None  # preserved from import
        self.search_filters = "FOCUS_FILTER_POLITICAL"  # raw filter string
        self.available_cond = ""  # raw HOI4 block content (inside available = { })
        self.bypass_cond = ""  # raw HOI4 block content (inside bypass = { })
        self.cancel_cond = ""  # raw HOI4 block content (inside cancel = { })
        self.will_lead_to_war_with = ""  # raw block content or target tag
        self.complete_tooltip = ""  # raw block content for complete_tooltip
        self.select_effect = ""  # raw block content (inside select_effect = { })
        self.bypass_effect = ""  # raw block content (inside bypass_effect = { })
        self.allow_branch = ""  # raw block content (inside allow_branch = { })
        self.text = ""  # custom localisation key override
        # conditional position offsets: [{"x": int, "y": int, "trigger": str}, ...]
        self.offsets: list[dict[str, object]] = []
        self.tree_idx = 0  # 0 = main tree; >0 = index into _extra_trees (1-based)

    @property
    def gfx(self) -> str:
        """Scalar image lookup key; structured script is retained separately."""
        return self._gfx

    @gfx.setter
    def gfx(self, value: object) -> None:
        preview, script = split_focus_icon(value)
        if script is not None:
            self._icon_script = script
        elif preview != getattr(self, "_gfx", None):
            self.__dict__.pop("_icon_script", None)
        self._gfx = preview

    def to_dict(self):
        data = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        data["gfx"] = self.gfx
        return data

    def duplicate(self, id: int):  # pylint: disable=redefined-builtin
        """Deep copy with an explicit fresh id and no stale imported coordinates."""
        nf = copy.deepcopy(self)
        nf.id = _bounded_id(id)
        for attr in ("_raw_gx", "_raw_gy", "_rel_dx", "_rel_dy"):
            if attr in nf.__dict__:
                del nf.__dict__[attr]
        for attr in (
            "_build_gx",
            "_build_gy",
            "_relative_pending",
            "_unresolved_prereqs",
            "_unresolved_mutex",
        ):
            nf.__dict__.pop(attr, None)
        return nf

    @staticmethod
    def from_dict(d: Mapping[str, object], *, legacy: bool = False) -> Focus:
        if not isinstance(d, Mapping):
            d = {}
        f = object.__new__(Focus)
        defaults = [
            ("id", 1),
            ("name", "focus_1"),
            ("loc_name", ""),
            ("icon", "⚔"),
            ("gfx", "GFX_goal_generic_political_pressure"),
            ("x", 0),
            ("y", 0),
            ("cost", 10),
            ("desc", ""),
            ("effects", []),
            ("prereqs", []),
            ("mutex", []),
            ("cancel_if_invalid", True),
            ("continue_if_invalid", False),
            ("available_if_capitulated", False),
            ("ai_will_do", 1),
            ("ai_will_do_raw", ""),
            ("relative_position_id", None),
            ("search_filters", "FOCUS_FILTER_POLITICAL"),
            ("available_cond", ""),
            ("bypass_cond", ""),
            ("cancel_cond", ""),
            ("will_lead_to_war_with", ""),
            ("complete_tooltip", ""),
            ("select_effect", ""),
            ("bypass_effect", ""),
            ("allow_branch", ""),
            ("text", ""),
            ("offsets", []),
            ("tree_idx", 0),
        ]
        for attr, default in defaults:
            setattr(f, attr, copy.deepcopy(default))
        for attr, value in d.items():
            coerce = _FIELD_COERCERS.get(attr)
            if coerce is not None:
                setattr(f, attr, coerce(value))
        # Restore semantic metadata after gfx regardless of JSON key ordering.
        script = d.get("_icon_script")
        if (
            isinstance(script, dict)
            and script.get("preview") == f.gfx
            and isinstance(script.get("value"), (dict, list))
        ):
            f._icon_script = copy.deepcopy(script)
        # Legacy pre-versioning project files stored pixel coords; grid
        # coords are indistinguishable from a multiple-of-96 pixel coord, so
        # this migration must never run on current-format or snapshot data.
        if legacy:
            if f.x >= 96 and f.x % 96 == 0:
                f.x = f.x // 96
            if f.y >= 96 and f.y % 96 == 0:
                f.y = f.y // 96
        return f
