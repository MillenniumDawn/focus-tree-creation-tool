from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FocusCanvasBundle:
    items: tuple[int, ...]
    lod: str
    draw_key: object = None
    image: object | None = None


__all__ = ["FocusCanvasBundle"]
