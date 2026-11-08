"""Headless integration for ModLoadingMixin._apply_md_additional_income.

Covers the three MD money-system files that the Additional Income wizard
touches atomically via WorkspaceFiles. Previous smokes only proved the
prompt dialog builds; these pin the file-transform contracts that actually
ship to the mod.
"""

from __future__ import annotations

import os

import pytest
from ui_fakes import AppFake

from hoi4cm.mod import scan_cache as scan_cache_mod


@pytest.fixture(autouse=True)
def isolate_scan_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "scan_cache"))


def _md_app(
    root: str | None, *, loaded: bool = True, language: str = "english"
) -> AppFake:
    app = AppFake()
    app.index.root = root
    app.index.loaded = loaded
    app.index.is_md = loaded
    app.app_config.loc_language = language
    return app


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _money_system_with_block(root: str) -> str:
    p = os.path.join(root, "common", "scripted_effects", "00_money_system.txt")
    _write(p, "calculate_additional_income_rate = {\n\t# existing\n}\n")
    return p


def _money_system_without_block(root: str) -> str:
    p = os.path.join(root, "common", "scripted_effects", "00_money_system.txt")
    _write(p, "# no block here\n")
    return p


def test_apply_income_injects_into_money_system_fixed(tmp_path):
    root = str(tmp_path)
    app = _md_app(root)
    p = _money_system_with_block(root)
    app.index.md_money_system_file = p
    # ensure the other two files exist so the method doesn't create them
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    app.index.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "base"\n')
    app.index.md_money_yml_file = yml

    saved, errs = app._apply_md_additional_income(
        "TAG_spirit", "var_test", "0.5", "TAG_spirit_tt", formula_type="fixed"
    )
    assert not errs
    assert any("00_money_system" in s for s in saved)
    txt = _read(p)
    assert "has_idea = TAG_spirit" in txt
    assert "set_variable = { var_test = 0.5 }" in txt
    assert "additional_income_rate = var_test" in txt


def test_apply_income_preserves_latin1_bytes_around_insertion(tmp_path):
    root = str(tmp_path)
    app = _md_app(root)
    p = os.path.join(root, "common", "scripted_effects", "00_money_system.txt")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    prefix = b"header = 1\r\ncalculate_additional_income_rate = {\r\n\t# caf\xe9\r\n"
    suffix = b"}\r\nfooter = 2\r\n"
    original = prefix + suffix
    with open(p, "wb") as fh:
        fh.write(original)
    app.index.md_money_system_file = p
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    app.index.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    yml_original = b"l_english:\r\n # caf\xe9\r\n"
    os.makedirs(os.path.dirname(yml), exist_ok=True)
    with open(yml, "wb") as fh:
        fh.write(yml_original)
    app.index.md_money_yml_file = yml

    saved, errs = app._apply_md_additional_income(
        "TAG_spirit", "var_test", "0.5", "TAG_spirit_tt"
    )

    assert not errs
    with open(p, "rb") as fh:
        updated = fh.read()
    assert b"caf\xe9" in updated
    assert b"\xef\xbf\xbd" not in updated
    insertion_point = original.index(b"}")
    assert updated.startswith(original[:insertion_point])
    assert updated.endswith(original[insertion_point:])
    inserted = updated[len(original[:insertion_point]) : -len(suffix)]
    assert b"\n" in inserted
    assert b"\n" not in inserted.replace(b"\r\n", b"")
    with open(yml, "rb") as fh:
        updated_yml = fh.read()
    assert updated_yml.startswith(yml_original)
    assert b"caf\xe9" in updated_yml
    assert b"ADDITIONAL_INCOME_REVENUES_TOOLTIP" in updated_yml
    assert b"\n" not in updated_yml.replace(b"\r\n", b"")


def test_apply_income_gdp_pct_and_population(tmp_path):
    root = str(tmp_path)
    app = _md_app(root)
    for formula, expected in [
        ("gdp_pct", "gdp_total"),
        ("population", "population_total"),
    ]:
        p = _money_system_with_block(root)
        app.index.md_money_system_file = p
        sloc = os.path.join(
            root, "common", "scripted_localisation", "money_scripted_localization.txt"
        )
        _write(sloc, "")
        app.index.md_money_scripted_loc_file = sloc
        yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
        _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "x"\n')
        app.index.md_money_yml_file = yml
        saved, errs = app._apply_md_additional_income(
            f"ID_{formula}", f"var_{formula}", "1.0", "tt", formula_type=formula
        )
        assert not errs
        txt = _read(p)
        assert expected in txt
        assert f"var_{formula}" in txt


def test_apply_income_idempotent_skips_duplicate(tmp_path):
    root = str(tmp_path)
    app = _md_app(root)
    p = _money_system_with_block(root)
    app.index.md_money_system_file = p
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    app.index.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "x"\n')
    app.index.md_money_yml_file = yml
    app._apply_md_additional_income("TAG_spirit", "var_test", "0.5", "tt")
    saved2, errs2 = app._apply_md_additional_income(
        "TAG_spirit", "var_test", "0.5", "tt"
    )
    assert not errs2
    assert any("already contains" in s for s in saved2)
    txt = _read(p)
    assert txt.count("has_idea = TAG_spirit") == 1


def test_apply_income_missing_block_reports_error(tmp_path):
    root = str(tmp_path)
    app = _md_app(root)
    p = _money_system_without_block(root)
    app.index.md_money_system_file = p
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    app.index.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "x"\n')
    app.index.md_money_yml_file = yml
    saved, errs = app._apply_md_additional_income("TAG_spirit", "var_test", "0.5", "tt")
    assert any("Could not find" in e for e in errs)


def test_apply_income_no_mod_loaded(tmp_path):
    app = _md_app(None, loaded=False)
    saved, errs = app._apply_md_additional_income("TAG_spirit", "var_test", "0.5", "tt")
    assert saved == []
    assert any("No mod loaded" in e for e in errs)


def test_apply_income_creates_missing_sloc_and_yml(tmp_path):
    root = str(tmp_path)
    app = _md_app(root)
    p = _money_system_with_block(root)
    app.index.md_money_system_file = p
    # do not create sloc/yml beforehand — let the method create them
    app.index.md_money_scripted_loc_file = ""
    app.index.md_money_yml_file = ""
    # ensure scan finds nothing
    app.index.rescan_md_money(app.app_config.loc_language)
    saved, errs = app._apply_md_additional_income(
        "NEW_spirit", "var_new", "2.0", "NEW_tt"
    )
    assert not errs
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    assert os.path.isfile(sloc)
    assert os.path.isfile(yml)
    assert "additional_income_summary_NEW_spirit" in _read(sloc)
    assert "[additional_income_summary_NEW_spirit]" in _read(yml)


def test_apply_income_creates_configured_language_yml(tmp_path):
    root = str(tmp_path)
    app = _md_app(root, language="french")
    app.index.md_money_system_file = _money_system_with_block(root)
    app.index.md_money_scripted_loc_file = ""
    app.index.md_money_yml_file = ""

    saved, errs = app._apply_md_additional_income(
        "NEW_spirit", "var_new", "2.0", "NEW_tt"
    )

    yml = os.path.join(root, "localisation", "french", "MD_money_l_french.yml")
    assert not errs
    assert any("MD_money_l_french.yml" in path for path in saved)
    assert _read(yml).startswith("\ufeffl_french:\n")


def test_apply_income_appends_to_existing_tooltip(tmp_path):
    root = str(tmp_path)
    app = _md_app(root)
    p = _money_system_with_block(root)
    app.index.md_money_system_file = p
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    app.index.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "first line"\n')
    app.index.md_money_yml_file = yml
    app._apply_md_additional_income("SPIRIT_A", "var_a", "0.1", "tt_a")
    app._apply_md_additional_income("SPIRIT_B", "var_b", "0.2", "tt_b")
    txt = _read(yml)
    assert "[additional_income_summary_SPIRIT_A]" in txt
    assert "[additional_income_summary_SPIRIT_B]" in txt


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("terminated", [False, True])
@pytest.mark.parametrize("encoding", ["utf-8-sig", "latin-1"])
@pytest.mark.parametrize("path_kind", ["wizard_tooltip", "money_tooltip"])
def test_income_localisation_append_separates_entries(
    tmp_path, newline, terminated, encoding, path_kind
):
    from hoi4cm.focus_tree.loc import parse_loc_values
    from hoi4cm.wizards.additional_income import _save_tooltip_localisation

    root = str(tmp_path)
    app = _md_app(root)
    path = tmp_path / "localisation" / "english" / "MD_money_l_english.yml"
    path.parent.mkdir(parents=True)
    original_text = f'l_english:{newline} OLD: "Café"' + (newline if terminated else "")
    original = original_text.encode(encoding)
    path.write_bytes(original)
    if path_kind == "wizard_tooltip":
        app.edit_loc_file = str(path)
        result = _save_tooltip_localisation(app, "TAG_spirit", "var_test", "TAG_tt")
        assert not any(line.startswith("❌") for line in result)
        key = "TAG_tt"
    else:
        app.index.md_money_system_file = _money_system_with_block(root)
        sloc = tmp_path / "common" / "scripted_localisation" / "money.txt"
        sloc.parent.mkdir(parents=True)
        sloc.write_text("", encoding="utf-8")
        app.index.md_money_scripted_loc_file = str(sloc)
        app.index.md_money_yml_file = str(path)
        _saved, errors = app._apply_md_additional_income(
            "TAG_spirit", "var_test", "0.5", "TAG_tt"
        )
        assert not errors
        key = "ADDITIONAL_INCOME_REVENUES_TOOLTIP"
    after = path.read_bytes()
    assert after.startswith(original)
    assert after.count(b"\xef\xbb\xbf") == (1 if encoding == "utf-8-sig" else 0)
    text = after.decode(encoding)
    assert text.startswith(original_text + ("" if terminated else newline))
    assert key in parse_loc_values(text)
    if newline == "\r\n":
        assert "\n" not in text.replace("\r\n", "")
    else:
        assert "\r" not in text


def test_wizard_tooltip_existing_key_is_unchanged(tmp_path):
    from hoi4cm.wizards.additional_income import _save_tooltip_localisation

    app = _md_app(str(tmp_path))
    path = tmp_path / "existing.yml"
    original = b'l_english:\n TAG_tt:0 "Keep me"'
    path.write_bytes(original)
    app.edit_loc_file = str(path)
    assert not _save_tooltip_localisation(app, "TAG_spirit", "var_test", "TAG_tt")
    assert path.read_bytes() == original


def test_wizard_tooltip_creates_file_and_reports_missing_selection(tmp_path):
    from hoi4cm.wizards.additional_income import _save_tooltip_localisation

    app = _md_app(str(tmp_path))
    app.edit_loc_file = str(tmp_path / "missing.yml")
    errors = _save_tooltip_localisation(app, "TAG_spirit", "var_test", "TAG_tt")
    assert any("no longer exists" in error for error in errors)
    assert not os.path.exists(app.edit_loc_file)
    app.edit_loc_file = ""
    result = _save_tooltip_localisation(app, "TAG_spirit", "var_test", "TAG_tt")
    target = tmp_path / "localisation" / "english" / "TAG_spirit_l_english.yml"
    assert any("wrote tooltip localisation" in line for line in result)
    assert target.read_bytes().startswith(b"\xef\xbb\xbfl_english:\n TAG_tt:")
