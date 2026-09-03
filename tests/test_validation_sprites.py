from typing import cast

import hoi4_content_maker as m
from hoi4cm.focus_tree.validate import validate_document
from hoi4cm.models import Focus


def _host() -> m.App:
    return cast(m.App, object())


def _focus(fid: int, gfx: str) -> Focus:
    f = Focus(0, 0)
    f.id = fid
    f.name = f"focus_{fid}"
    f.gfx = gfx
    f.effects = [{"type": "dummy", "fields": {}}]
    return f


def test_validation_sprites_returns_none_when_unloaded(monkeypatch):
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "sprites", {"GFX_foo": "/x"})
    assert m.App._validation_sprites(_host()) is None


def test_validation_sprites_returns_none_when_empty(monkeypatch):
    monkeypatch.setattr(m.MOD, "loaded", True)
    monkeypatch.setattr(m.MOD, "sprites", {})
    assert m.App._validation_sprites(_host()) is None


def test_validation_sprites_snapshot_survives_clear(monkeypatch):
    live = {"GFX_foo": "/x"}
    monkeypatch.setattr(m.MOD, "loaded", True)
    monkeypatch.setattr(m.MOD, "sprites", live)

    snapshot = m.App._validation_sprites(_host())
    assert snapshot == {"GFX_foo": "/x"}
    assert snapshot is not live

    live.clear()
    issues = validate_document({1: _focus(1, "GFX_foo")}, sprites=snapshot)
    assert not any(it.code == "gfx_missing" for it in issues)
