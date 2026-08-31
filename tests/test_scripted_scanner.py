"""Scripted effect, trigger, and on-action scanner coverage."""

import os

import pytest

from hoi4cm.mod import ModContext
from hoi4cm.mod import scan_cache as scan_cache_mod
from hoi4cm.ui.effects_panel import EffectsMixin, _augment_scripted_suggestions


@pytest.fixture(autouse=True)
def isolate_scan_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(
        scan_cache_mod, "STATE_DIR", str(tmp_path_factory.mktemp("hoi4cm_state"))
    )


def test_extract_scripted_names_uses_only_top_level_blocks():
    source = """
    first_effect = {
        nested_effect = { }
    }
    second_effect = {
        limit = { nested_trigger = yes }
    }
    _private = { }
    loose_token
    """

    assert ModContext._extract_scripted_names(source) == [
        "first_effect",
        "second_effect",
        "_private",
    ]


def test_extract_on_actions_reads_wrapped_hook_names():
    source = """
    on_actions = {
        on_game_start = { effect = { } }
        on_monthly_pulse = { }
        _private = { }
        loose_hook
    }
    """

    assert ModContext._extract_on_actions(source) == [
        "on_game_start",
        "on_monthly_pulse",
        "_private",
    ]
    assert ModContext._extract_on_actions("on_shutdown = { }") == ["on_shutdown"]


def test_scan_scripted_names_reads_mixed_encoding_files(tmp_path):
    scripted_dir = tmp_path / "common" / "scripted_effects"
    scripted_dir.mkdir(parents=True)
    (scripted_dir / "latin.txt").write_bytes(
        "# café\nlatin_effect = { }\n".encode("latin-1")
    )

    context = ModContext()
    context.scan(str(tmp_path))

    assert context.scripted_effect_ids == ["latin_effect"]


def test_scan_scripted_names_deduplicates_in_file_order_and_resets(tmp_path):
    for directory in ("scripted_effects", "scripted_triggers", "on_actions"):
        (tmp_path / "common" / directory).mkdir(parents=True)
    (tmp_path / "common" / "scripted_effects" / "a.txt").write_text(
        "first_effect = { }\nshared_effect = { }\n"
    )
    (tmp_path / "common" / "scripted_effects" / "b.txt").write_text(
        "shared_effect = { }\nlast_effect = { }\n"
    )
    (tmp_path / "common" / "scripted_triggers" / "a.txt").write_text(
        "first_trigger = { }\nshared_trigger = { }\n"
    )
    (tmp_path / "common" / "scripted_triggers" / "b.txt").write_text(
        "shared_trigger = { }\nlast_trigger = { }\n"
    )
    (tmp_path / "common" / "on_actions" / "a.txt").write_text(
        "on_actions = { on_start = { } on_shared = { } }\n"
    )
    (tmp_path / "common" / "on_actions" / "b.txt").write_text(
        "on_actions = { on_shared = { } on_end = { } }\n"
    )

    context = ModContext()
    context.scripted_effect_ids = ["stale_effect"]
    context.scripted_trigger_ids = ["stale_trigger"]
    context.on_action_ids = ["stale_action"]

    context.scan(str(tmp_path))

    assert context.scripted_effect_ids == [
        "first_effect",
        "shared_effect",
        "last_effect",
    ]
    assert context.scripted_trigger_ids == [
        "first_trigger",
        "shared_trigger",
        "last_trigger",
    ]
    assert context.on_action_ids == ["on_start", "on_shared", "on_end"]

    context.scan(str(tmp_path / "empty"))

    assert context.scripted_effect_ids == []
    assert context.scripted_trigger_ids == []
    assert context.on_action_ids == []


def test_scan_scripted_names_uses_file_cache(tmp_path, monkeypatch):
    scripted_dir = tmp_path / "common" / "scripted_effects"
    scripted_dir.mkdir(parents=True)
    effect_file = scripted_dir / "effects.txt"
    effect_file.write_text("first_effect = { }\n")
    context = ModContext()

    context.scan(str(tmp_path))

    reads = []
    original_read = context._read
    monkeypatch.setattr(
        context,
        "_read",
        lambda path: (reads.append(path), original_read(path))[1],
    )
    context.scan(str(tmp_path))
    assert reads == []

    effect_file.write_text("changed_effect = { }\n")
    stat = effect_file.stat()
    os.utime(effect_file, (stat.st_atime, stat.st_mtime + 10))
    context.scan(str(tmp_path))

    assert reads == [str(effect_file)]
    assert context.scripted_effect_ids == ["changed_effect"]


def test_effects_mixin_uses_scanned_scripted_suggestions(monkeypatch):
    monkeypatch.setattr("hoi4cm.ui.effects_panel.MOD.loaded", True)
    monkeypatch.setattr(
        "hoi4cm.ui.effects_panel.MOD.scripted_effect_ids", ["custom_effect"]
    )
    monkeypatch.setattr(
        "hoi4cm.ui.effects_panel.MOD.scripted_trigger_ids", ["custom_trigger"]
    )
    monkeypatch.setattr("hoi4cm.ui.effects_panel.MOD.on_action_ids", ["custom_action"])

    class DummyApp(EffectsMixin):
        def _get_mod_suggestions(self, etype, fname):
            return ["built_in"]

    assert EffectsMixin._get_effect_suggestions(DummyApp(), "x", "effect") == [
        "built_in",
        "custom_effect",
    ]
    assert EffectsMixin._get_effect_suggestions(DummyApp(), "x", "limit") == [
        "built_in",
        "custom_trigger",
    ]
    assert EffectsMixin._get_effect_suggestions(DummyApp(), "x", "on_action") == [
        "built_in",
        "custom_action",
    ]


def test_augment_scripted_suggestions_sorts_matching_fields_only():
    base = ["zeta", "alpha"]
    effects = ["beta", "alpha"]
    triggers = ["delta", "alpha"]
    actions = ["gamma", "alpha"]

    assert _augment_scripted_suggestions(
        base,
        "effect",
        loaded=True,
        scripted_effect_ids=effects,
        scripted_trigger_ids=triggers,
        on_action_ids=actions,
    ) == ["alpha", "beta", "zeta"]
    assert _augment_scripted_suggestions(
        base,
        "limit",
        loaded=True,
        scripted_effect_ids=effects,
        scripted_trigger_ids=triggers,
        on_action_ids=actions,
    ) == ["alpha", "delta", "zeta"]
    assert _augment_scripted_suggestions(
        base,
        "on_action",
        loaded=True,
        scripted_effect_ids=effects,
        scripted_trigger_ids=triggers,
        on_action_ids=actions,
    ) == ["alpha", "gamma", "zeta"]
    assert (
        _augment_scripted_suggestions(
            base,
            "country",
            loaded=True,
            scripted_effect_ids=effects,
            scripted_trigger_ids=triggers,
            on_action_ids=actions,
        )
        is base
    )
    assert (
        _augment_scripted_suggestions(
            base,
            "effect",
            loaded=False,
            scripted_effect_ids=effects,
            scripted_trigger_ids=triggers,
            on_action_ids=actions,
        )
        is base
    )
