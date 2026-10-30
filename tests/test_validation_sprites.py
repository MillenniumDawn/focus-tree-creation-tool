from types import SimpleNamespace
from typing import cast

import hoi4_content_maker as m
from hoi4cm.focus_tree.validate import validate_document
from hoi4cm.mod.index import ModIndex
from hoi4cm.models import Focus


def _host(
    loaded: bool = False, sprites: dict[str, str] | None = None
) -> SimpleNamespace:
    index = ModIndex()
    index.loaded = loaded
    if sprites is not None:
        index.sprites = sprites
    return SimpleNamespace(index=index, edit_loc_file="")


def _focus(fid: int, gfx: str) -> Focus:
    f = Focus(id=1, x=0, y=0)
    f.id = fid
    f.name = f"focus_{fid}"
    f.gfx = gfx
    f.effects = [{"type": "dummy", "fields": {}}]
    return f


def test_validation_sprites_returns_none_when_unloaded():
    host = cast(m.App, _host(False, {"GFX_foo": "/x"}))
    assert m.App._validation_sprites(host) is None


def test_validation_sprites_returns_none_when_empty():
    assert m.App._validation_sprites(cast(m.App, _host(True, {}))) is None


def test_validation_sprites_snapshot_survives_clear():
    live = {"GFX_foo": "/x"}
    snapshot = m.App._validation_sprites(cast(m.App, _host(True, live)))
    assert snapshot == {"GFX_foo": "/x"}
    assert snapshot is not live

    live.clear()
    issues = validate_document({1: _focus(1, "GFX_foo")}, sprites=snapshot)
    assert not any(it.code == "gfx_missing" for it in issues)


def test_run_validation_snapshots_sprites_before_worker(monkeypatch):
    live = {"GFX_foo": "/x"}
    captured: list[object] = []

    def fake_validate(_focuses, sprites=None, **_kwargs):
        captured.append(sprites)
        return []

    monkeypatch.setattr(m, "validate_document", fake_validate)

    def fake_run_bg(_widget, work, _on_done, **_kwargs):
        live.clear()
        work()

    monkeypatch.setattr(m, "run_bg", fake_run_bg)

    host = _host(True, live)
    host.focuses = {1: _focus(1, "GFX_foo")}
    host._validation_job = object()
    host._lifecycle = SimpleNamespace(begin=lambda scope: None)
    host._validation_loc_keys = lambda: None
    host._apply_validation_result = lambda _issues: None
    host._validation_sprites = m.App._validation_sprites.__get__(host)
    host._run_validation = m.App._run_validation.__get__(host)

    host._run_validation()

    sprites = captured[0]
    assert sprites == {"GFX_foo": "/x"}
    assert sprites is not live
    assert live == {}
