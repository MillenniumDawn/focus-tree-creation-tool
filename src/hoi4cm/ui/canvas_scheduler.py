from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag, auto


class RedrawChannel(IntFlag):
    VIEW = auto()
    SCENE = auto()
    FOCUS_LIST = auto()


@dataclass(frozen=True)
class RedrawRequest:
    channels: RedrawChannel
    reasons: frozenset[str]


class DirtyRedrawState:
    def __init__(self) -> None:
        self._channels = RedrawChannel(0)
        self._reasons: set[str] = set()
        self._pending = False

    @property
    def pending(self) -> bool:
        return self._pending

    def request(self, channels: RedrawChannel, reason: str) -> bool:
        self._channels |= channels
        self._reasons.add(reason)
        should_schedule = not self._pending
        self._pending = True
        return should_schedule

    def consume(self) -> RedrawRequest:
        request = RedrawRequest(self._channels, frozenset(self._reasons))
        self._channels = RedrawChannel(0)
        self._reasons.clear()
        self._pending = False
        return request


__all__ = ["DirtyRedrawState", "RedrawChannel", "RedrawRequest"]
