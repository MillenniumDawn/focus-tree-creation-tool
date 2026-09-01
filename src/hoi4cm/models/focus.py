"""Focus data model — the canvas item at the heart of every focus tree."""

import copy


class Focus:
    """A single national focus in the editor canvas."""

    _next = 0

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

    def __init__(self, x=0, y=0):
        Focus._next += 1
        self.id = Focus._next
        self.name = f"focus_{self.id}"
        self.loc_name = ""
        self.icon = "⚔"
        self.gfx = "GFX_goal_generic_political_pressure"
        self.x = x
        self.y = y
        self.cost: int | float = 10
        self.desc = ""
        self.effects = []  # [{"type":str,"fields":{name:val}}]
        self.prereqs = []  # [[fid,...]] AND of OR-groups
        self.mutex = []  # [fid,...]
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
        self.offsets = []
        self.tree_idx = 0  # 0 = main tree; >0 = index into _extra_trees (1-based)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def duplicate(self):
        """Deep copy with a fresh counter id and no stale imported coordinates."""
        nf = copy.deepcopy(self)
        Focus._next += 1
        nf.id = Focus._next
        for attr in ("_raw_gx", "_raw_gy", "_rel_dx", "_rel_dy"):
            if attr in nf.__dict__:
                del nf.__dict__[attr]
        return nf

    @staticmethod
    def from_dict(d, *, legacy=False):
        f = object.__new__(Focus)
        for k, v in d.items():
            setattr(f, k, v)
        # Legacy pre-versioning project files stored pixel coords; grid
        # coords are indistinguishable from a multiple-of-96 pixel coord, so
        # this migration must never run on current-format or snapshot data.
        if legacy:
            if f.x >= 96 and f.x % 96 == 0:
                f.x = f.x // 96
            if f.y >= 96 and f.y % 96 == 0:
                f.y = f.y // 96
        defaults = [
            ("mutex", []),
            ("cancel_if_invalid", True),
            ("continue_if_invalid", False),
            ("available_if_capitulated", False),
            ("ai_will_do", 1),
            ("gfx", "GFX_goal_generic_political_pressure"),
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
            ("loc_name", ""),
            ("offsets", []),
            ("ai_will_do_raw", ""),
            ("tree_idx", 0),
        ]
        for attr, default in defaults:
            if not hasattr(f, attr):
                setattr(f, attr, default)
        if f.id >= Focus._next:
            Focus._next = f.id + 1
        return f
