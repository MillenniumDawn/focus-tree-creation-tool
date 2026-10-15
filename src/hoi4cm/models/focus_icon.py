"""Keep imported icon script separate from the scalar UI preview name."""

from copy import deepcopy

DEFAULT_GFX = "GFX_goal_generic_political_pressure"


def split_focus_icon(value: object) -> tuple[str, dict[str, object] | None]:
    """Return a usable preview and, for structured icons, lossless script data.

    Repeated icon declarations are ordered lists; conditional blocks use sprite
    names as keys. Neither should be passed to image lookup as a hash key.
    """
    if isinstance(value, str):
        return value, None
    if isinstance(value, list):
        preview = split_focus_icon(value[0])[0] if value else DEFAULT_GFX
    elif isinstance(value, dict):
        preview = next(
            (key for key in value if isinstance(key, str) and not key.startswith("_")),
            DEFAULT_GFX,
        )
    else:
        return "", None
    return preview, {"preview": preview, "value": deepcopy(value)}
