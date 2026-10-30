"""Tk-thread PhotoImage cache for scanned sprite names.

The canvas and thumbnail grid use :class:`hoi4cm.ui.image_broker.ImageBroker`.
This cache is the synchronous gfx-name lookup the post-load probe and wizard
callers still use. It is owned by the App and must not be handed to a worker.
"""

from __future__ import annotations

import os
from collections.abc import Collection, Mapping
from typing import Any

from hoi4cm.core.lru import LRUCache

_SPRITE_IMG_CACHE_SIZE = 512
_PillowState = tuple[bool, Any, Any]
_PIL_STATE: _PillowState | None = None


def _get_pillow_state() -> _PillowState:
    """Return Pillow's import state, publishing all three values together."""
    global _PIL_STATE
    state = _PIL_STATE
    if state is None:
        from hoi4cm.core.image import PIL_OK, PILImage, PILImageTk

        state = (PIL_OK, PILImage, PILImageTk)
        _PIL_STATE = state
    return state


class SpriteImageCache:
    """Bounded gfx-name PhotoImage cache. Construct and clear it on the Tk thread."""

    def __init__(self, maxsize: int = _SPRITE_IMG_CACHE_SIZE) -> None:
        self.images = LRUCache(maxsize)
        self.errors: list[str] = []

    def get_image(
        self,
        sprites: Mapping[str, str],
        gfx_name: str,
        size: tuple[int, int] = (64, 64),
    ):
        """Return a PhotoImage for gfx_name, or None.

        Caches both successes and failures so repeated lookups do not reopen
        the same file. ``sprites`` is the index's name-to-path map, passed in
        so this cache does not hold the index.
        """
        if not gfx_name:
            return None
        key = (gfx_name, size)
        if key in self.images:
            return self.images[key]

        path = sprites.get(gfx_name)
        if not path:
            self.images[key] = None
            self.errors.append("NOT IN SPRITES: " + gfx_name)
            return None
        if not os.path.exists(path):
            self.images[key] = None
            self.errors.append("FILE NOT FOUND: " + path)
            return None

        pil_ok, pil_image, pil_image_tk = _get_pillow_state()
        if not pil_ok or pil_image is None or pil_image_tk is None:
            self.images[key] = None
            self.errors.append("Pillow not available")
            return None

        try_paths = [path]
        if path.lower().endswith(".dds"):
            stem = os.path.splitext(path)[0]
            for alt_ext in (".png", ".tga", ".jpg"):
                alt = stem + alt_ext
                if os.path.exists(alt):
                    try_paths.append(alt)

        resample = getattr(pil_image, "LANCZOS", getattr(pil_image, "ANTIALIAS", 1))
        last_err = ""
        for try_path in try_paths:
            try:
                img = pil_image.open(try_path).convert("RGBA")
                img = img.resize(size, resample)
                photo = pil_image_tk.PhotoImage(img)
                self.images[key] = photo
                return photo
            except (OSError, ValueError, RuntimeError, AttributeError) as exc:
                last_err = f"{os.path.basename(try_path)}: {exc}"

        self.images[key] = None
        self.errors.append(f"LOAD FAILED {gfx_name}: {last_err}")
        return None

    def clear(self) -> list[Any]:
        """Drop every cached image and return the old values."""
        self.errors.clear()
        return self.images.clear()

    def evict(self, names: Collection[str]) -> list[Any]:
        """Drop cached images for the named sprites and return those values."""
        if not names:
            return []
        changed = set(names)
        return self.images.evict(lambda key: key[0] in changed)


__all__ = ["SpriteImageCache"]
