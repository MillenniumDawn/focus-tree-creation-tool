"""Dark Professional Theme — colours, grid sizes, icon list.

The monolith reads these as module-level globals. They're now a flat
import-time constant module so the rest of the package can pull them
without depending on the launcher.
"""

# Colour palette
BG_DARK = "#0d1117"  # deepest dark  (topbar / chrome)
BG_PANEL = "#161b27"  # dark navy     (sidebar bg)
BG_CARD = "#1e2435"  # card / input bg
CANVAS_BG = "#111827"  # canvas dark
GOLD = "#f0c040"  # cost text yellow
GOLD_DIM = "#6b7280"  # dimmed
GOLD_LT = "#f9fafb"  # bright white text
TEXT = "#e2e8f0"  # near-white primary text
TEXT_DIM = "#6b7280"  # muted grey labels
BORDER = "#2d3748"  # subtle border
BORDER_G = "#374151"  # slightly brighter border
RED = "#ef4444"  # delete / error
GREEN = "#22c55e"  # save / ok
BLUE = "#3b82f6"  # primary accent (prereqs / connect)
ORANGE = "#f97316"  # mutex
SEL_BG = "#1d4ed8"  # selection bg
TEAL = "#2dd4bf"  # teal accent
PURPLE = "#a78bfa"  # purple accent
BG_HOVER = "#1a2030"  # hover bg for menu items
YELLOW = "#fbbf24"  # tree name / warning accent

# Focus card colours
FC_BG = "#1a2035"  # dark card body
FC_SEL = "#1e3a6e"  # selected card (blue tint)
FC_BORDER = "#374151"  # subtle card border
FC_SEL_BD = "#3b82f6"  # selected border (bright blue)

# Connection line colours
PREREQ_COL = "#3b82f6"  # blue arrow  (prerequisite)
MUTEX_COL = "#f97316"  # orange dashed (mutually exclusive)

# Grid / layout
XGRID = 96  # hoi4modutilities exact: xGridSize=96
YGRID = 130  # yGridSize=130
BOX = 52  # focus card rendered size

# Icon list
ICONS = [
    "⚔",
    "🛡",
    "🏭",
    "🌾",
    "💰",
    "🔬",
    "⚙",
    "🗺",
    "✊",
    "🏛",
    "★",
    "⚡",
    "🐉",
    "🎖",
    "📜",
    "🔔",
    "🌊",
    "🔥",
    "❄",
    "☠",
]


__all__ = [
    "BG_CARD",
    "BG_DARK",
    "BG_HOVER",
    "BG_PANEL",
    "BLUE",
    "BORDER",
    "BORDER_G",
    "BOX",
    "CANVAS_BG",
    "FC_BG",
    "FC_BORDER",
    "FC_SEL",
    "FC_SEL_BD",
    "GOLD",
    "GOLD_DIM",
    "GOLD_LT",
    "GREEN",
    "ICONS",
    "MUTEX_COL",
    "ORANGE",
    "PREREQ_COL",
    "PURPLE",
    "RED",
    "SEL_BG",
    "TEAL",
    "TEXT",
    "TEXT_DIM",
    "XGRID",
    "YELLOW",
    "YGRID",
]
