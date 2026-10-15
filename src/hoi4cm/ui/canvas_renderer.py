from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FocusCanvasBundle:
    items: tuple[int, ...]
    lod: str
    draw_key: object = None
    image: object | None = None
    bindings: list[str] = field(default_factory=list)


__all__ = ["FocusCanvasBundle"]
