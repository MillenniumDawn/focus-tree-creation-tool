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


def _write_locale(directory, code, payload):
    (directory / f"{code}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


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


def test_german_language_is_selectable_and_loaded(restore_i18n_state, fake_config):
    assert i18n_mod.I18N_LANGS["de"] == "Deutsch"

    i18n_mod.set_language("de")

    assert i18n_mod.I18N_LANG == "de"
    assert i18n_mod.tr("common.cancel") == "Abbrechen"
    assert _read_json_or_empty(fake_config).get("language") == "de"


def test_set_language_rejects_unknown(restore_i18n_state, fake_config, monkeypatch):
    monkeypatch.setattr(i18n_mod, "cfg_save", lambda d: True)
    assert i18n_mod.set_language("xx_YY") is True  # not in I18N_LANGS
    assert i18n_mod.I18N_LANG == "en"  # falls back to en


def test_set_language_reports_save_failure(
    restore_i18n_state, fake_config, monkeypatch
):
    monkeypatch.setattr(i18n_mod, "cfg_save", lambda d: False)
    assert i18n_mod.set_language("de") is False
    assert i18n_mod.I18N_LANG == "de"


def test_get_language_tracks_set_language(restore_i18n_state, fake_config):
    """get_language() must reflect the live value, not a stale snapshot —
    the settings dialog relies on this to show the current language."""
    i18n_mod.set_language("en")
    assert i18n_mod.get_language() == "en"
    i18n_mod.set_language("zh_CN")
    assert i18n_mod.get_language() == "zh_CN"


def test_shipped_languages_are_discovered_with_english_first():
    assert list(i18n_mod.I18N_LANGS.items()) == [
        ("en", "English"),
        ("de", "Deutsch"),
        ("es", "Español"),
        ("zh_CN", "简体中文"),
    ]


def test_discover_languages_reads_meta_display_names(tmp_path):
    _write_locale(tmp_path, "zh_CN", {"_meta": {"display_name": "简体中文"}})
    _write_locale(tmp_path, "fr", {"_meta": {"display_name": "Français"}})
    _write_locale(tmp_path, "en", {"_meta": {"display_name": "English"}})

    assert list(i18n_mod.discover_languages(tmp_path).items()) == [
        ("en", "English"),
        ("fr", "Français"),
        ("zh_CN", "简体中文"),
    ]


def test_discover_languages_always_offers_english(tmp_path):
    assert i18n_mod.discover_languages(tmp_path) == {"en": "English"}
    assert i18n_mod.discover_languages(tmp_path / "missing") == {"en": "English"}


@pytest.mark.parametrize(
    "payload",
    [{"a.key": "text"}, {"_meta": {}}, {"_meta": {"display_name": ""}}, {"_meta": "x"}],
)
def test_discover_languages_falls_back_to_code_without_display_name(tmp_path, payload):
    _write_locale(tmp_path, "pt_BR", payload)

    assert i18n_mod.discover_languages(tmp_path)["pt_BR"] == "pt_BR"


def test_discover_languages_skips_unreadable_files(tmp_path):
    (tmp_path / "bad_json.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "bad_bytes.json").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "not_object.json").write_text("[1, 2]", encoding="utf-8")
    _write_locale(tmp_path, "de", {"_meta": {"display_name": "Deutsch"}})

    assert i18n_mod.discover_languages(tmp_path) == {"en": "English", "de": "Deutsch"}


def test_unknown_language_falls_back_to_english(restore_i18n_state, fake_config):
    i18n_mod._load_i18n("xx_YY")

    assert i18n_mod.get_language() == "en"


def test_missing_locale_file_leaves_inline_defaults_in_use(
    restore_i18n_state, fake_config, tmp_path, monkeypatch
):
    monkeypatch.setattr(i18n_mod, "_project_root", lambda: str(tmp_path))

    i18n_mod._load_i18n("en")

    assert i18n_mod.I18N_STRINGS == {}
    assert i18n_mod.tr("common.cancel", "Cancel") == "Cancel"


def test_meta_block_is_not_a_translation(restore_i18n_state):
    i18n_mod._load_i18n("de")

    assert "_meta" not in i18n_mod.I18N_STRINGS
    assert i18n_mod.tr("_meta") == "_meta"


def test_dropped_in_locale_file_is_selectable(
    restore_i18n_state, fake_config, tmp_path, monkeypatch
):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(
        locales,
        "fr",
        {"_meta": {"display_name": "Français"}, "common.cancel": "Annuler"},
    )
    monkeypatch.setattr(i18n_mod, "_project_root", lambda: str(tmp_path))
    monkeypatch.setattr(i18n_mod, "I18N_LANGS", i18n_mod.discover_languages(locales))

    i18n_mod.set_language("fr")

    assert i18n_mod.get_language() == "fr"
    assert i18n_mod.tr("common.cancel", "Cancel") == "Annuler"
    assert "_meta" not in i18n_mod.I18N_STRINGS
