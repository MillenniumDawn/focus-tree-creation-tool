from types import SimpleNamespace
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


def test_run_validation_snapshots_sprites_before_worker(monkeypatch):
    live = {"GFX_foo": "/x"}
    monkeypatch.setattr(m.MOD, "loaded", True)
    monkeypatch.setattr(m.MOD, "sprites", live)

    captured: list[object] = []

    def fake_validate(_focuses, sprites=None, **_kwargs):
        captured.append(sprites)
        return []

    monkeypatch.setattr(m, "validate_document", fake_validate)

    def fake_run_bg(_widget, work, _on_done, **_kwargs):
        live.clear()
        work()

    monkeypatch.setattr(m, "run_bg", fake_run_bg)

    host = SimpleNamespace(
        focuses={1: _focus(1, "GFX_foo")},
        _validation_job=object(),
        _lifecycle=SimpleNamespace(begin=lambda scope: None),
        _validation_loc_keys=lambda: None,
        _apply_validation_result=lambda _issues: None,
    )
    host._validation_sprites = m.App._validation_sprites.__get__(host)
    host._run_validation = m.App._run_validation.__get__(host)

    host._run_validation()

    sprites = captured[0]
    assert sprites == {"GFX_foo": "/x"}
    assert sprites is not live
    assert live == {}
