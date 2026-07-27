"""Tests for hoi4cm.core.i18n — locale loading and translation lookup."""

import json

import pytest

from hoi4cm.core import i18n as i18n_mod


@pytest.fixture
def restore_i18n_state():
    """Snapshot the module-level state and restore it after the test."""
    saved = (i18n_mod.I18N_LANG, dict(i18n_mod.I18N_STRINGS))
    yield
    i18n_mod.I18N_LANG, i18n_mod.I18N_STRINGS = saved


@pytest.fixture
def fake_config(tmp_path, monkeypatch):
    """Repoint cfg_load/cfg_save to a tmp JSON file so tests don't touch
    the real user config. Returns the path to the backing file."""
    config_file = tmp_path / "config.json"

    def fake_load():
        try:
            return json.loads(config_file.read_text())
        except FileNotFoundError, json.JSONDecodeError:
            return {}

    def fake_save(d):
        existing = fake_load()
        existing.update(d)
        config_file.write_text(json.dumps(existing))

    monkeypatch.setattr(i18n_mod, "cfg_load", fake_load)
    monkeypatch.setattr(i18n_mod, "cfg_save", fake_save)
    return config_file


def _read_json_or_empty(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError, json.JSONDecodeError:
        return {}


def test_tr_returns_default_when_key_missing(restore_i18n_state):
    assert i18n_mod.tr("definitely.not.a.key", "fallback text") == "fallback text"


def test_tr_returns_key_when_no_default(restore_i18n_state):
    assert i18n_mod.tr("definitely.not.a.key") == "definitely.not.a.key"


def test_tr_handles_format_kwargs(restore_i18n_state):
    assert i18n_mod.tr("count.label", "{count} items", count=3) == "3 items"


def test_tr_handles_missing_format_kwargs_gracefully(restore_i18n_state):
    # Bad format string in default returns the raw text, doesn't crash
    assert i18n_mod.tr("some.key", "hello {missing}") == "hello {missing}"


def test_known_english_keys_resolve(restore_i18n_state):
    """English locale should ship with at least the common.* keys used in
    the wizards. If this fails, the locales/en.json file went missing."""
    assert "en" in i18n_mod.I18N_LANGS
    i18n_mod._load_i18n("en")
    # common.cancel is used by every wizard's Cancel button
    assert i18n_mod.tr("common.cancel", "x") != "x"


def test_set_language_persists_and_loads(restore_i18n_state, fake_config):
    i18n_mod.set_language("zh_CN")
    assert i18n_mod.I18N_LANG == "zh_CN"
    assert _read_json_or_empty(fake_config).get("language") == "zh_CN"


def test_set_language_rejects_unknown(restore_i18n_state, fake_config, monkeypatch):
    monkeypatch.setattr(i18n_mod, "cfg_save", lambda d: None)
    i18n_mod.set_language("xx_YY")  # not in I18N_LANGS
    assert i18n_mod.I18N_LANG == "en"  # falls back to en


def test_get_language_tracks_set_language(restore_i18n_state, fake_config):
    """get_language() must reflect the live value, not a stale snapshot —
    the settings dialog relies on this to show the current language."""
    i18n_mod.set_language("en")
    assert i18n_mod.get_language() == "en"
    i18n_mod.set_language("zh_CN")
    assert i18n_mod.get_language() == "zh_CN"
