"""Focus data model — the canvas item at the heart of every focus tree."""


class Focus:
    """A single national focus in the editor canvas."""

    _next = 0

    def __init__(self, x=0, y=0):
        Focus._next += 1
        self.id = Focus._next
        self.name = f"focus_{self.id}"
        self.icon = "⚔"
        self.gfx = "GFX_goal_generic_political_pressure"
        self.x = x
        self.y = y
        self.cost = 10
        self.desc = ""
        self.effects = []  # [{"type":str,"fields":{name:val}}]
        self.prereqs = []  # [[fid,...]] AND of OR-groups
        self.mutex = []  # [fid,...]
        self.cancel_if_invalid = True
        self.continue_if_invalid = False
        self.available_if_capitulated = False
        self.ai_will_do = 1
        self.ai_will_do_raw = ""  # full raw ai_will_do block if imported
        self.relative_position_id = None  # preserved from import
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
        self._items = []
        self._draw_key = None

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @staticmethod
    def from_dict(d):
        f = object.__new__(Focus)
        f._items = []
        f._draw_key = None
        for k, v in d.items():
            setattr(f, k, v)
        # Migrate old pixel-based coords to grid integers
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
