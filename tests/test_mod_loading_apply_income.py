"""Headless integration for ModLoadingMixin._apply_md_additional_income.

Covers the three MD money-system files that the Additional Income wizard
touches atomically via WorkspaceFiles. Previous smokes only proved the
prompt dialog builds; these pin the file-transform contracts that actually
ship to the mod.
"""

from __future__ import annotations

import copy
import os

import pytest

from hoi4cm.mod import MOD
from hoi4cm.mod import scan_cache as scan_cache_mod
from hoi4cm.ui.mod_loading import ModLoadingMixin


@pytest.fixture(autouse=True)
def isolate_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "scan_cache"))
    snapshot = copy.deepcopy(MOD.__dict__)
    MOD.loaded = True
    MOD.root = str(tmp_path)
    yield
    MOD.__dict__.clear()
    MOD.__dict__.update(snapshot)


class _FakeApp(ModLoadingMixin):
    pass


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
    MOD.root = root
    MOD.loaded = True
    p = _money_system_with_block(root)
    MOD.md_money_system_file = p
    # ensure the other two files exist so the method doesn't create them
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    MOD.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "base"\n')
    MOD.md_money_yml_file = yml

    app = _FakeApp()
    saved, errs = app._apply_md_additional_income(
        "TAG_spirit", "var_test", "0.5", "TAG_spirit_tt", formula_type="fixed"
    )
    assert not errs
    assert any("00_money_system" in s for s in saved)
    txt = _read(p)
    assert "has_idea = TAG_spirit" in txt
    assert "set_variable = { var_test = 0.5 }" in txt
    assert "additional_income_rate = var_test" in txt


def test_apply_income_gdp_pct_and_population(tmp_path):
    root = str(tmp_path)
    MOD.root = root
    MOD.loaded = True
    for formula, expected in [
        ("gdp_pct", "gdp_total"),
        ("population", "population_total"),
    ]:
        p = _money_system_with_block(root)
        MOD.md_money_system_file = p
        sloc = os.path.join(
            root, "common", "scripted_localisation", "money_scripted_localization.txt"
        )
        _write(sloc, "")
        MOD.md_money_scripted_loc_file = sloc
        yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
        _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "x"\n')
        MOD.md_money_yml_file = yml
        app = _FakeApp()
        saved, errs = app._apply_md_additional_income(
            f"ID_{formula}", f"var_{formula}", "1.0", "tt", formula_type=formula
        )
        assert not errs
        txt = _read(p)
        assert expected in txt
        assert f"var_{formula}" in txt


def test_apply_income_idempotent_skips_duplicate(tmp_path):
    root = str(tmp_path)
    MOD.root = root
    MOD.loaded = True
    p = _money_system_with_block(root)
    MOD.md_money_system_file = p
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    MOD.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "x"\n')
    MOD.md_money_yml_file = yml
    app = _FakeApp()
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
    MOD.root = root
    MOD.loaded = True
    p = _money_system_without_block(root)
    MOD.md_money_system_file = p
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    MOD.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "x"\n')
    MOD.md_money_yml_file = yml
    app = _FakeApp()
    saved, errs = app._apply_md_additional_income("TAG_spirit", "var_test", "0.5", "tt")
    assert any("Could not find" in e for e in errs)


def test_apply_income_no_mod_loaded(tmp_path):
    MOD.loaded = False
    MOD.root = None
    app = _FakeApp()
    saved, errs = app._apply_md_additional_income("TAG_spirit", "var_test", "0.5", "tt")
    assert saved == []
    assert any("No mod loaded" in e for e in errs)


def test_apply_income_creates_missing_sloc_and_yml(tmp_path):
    root = str(tmp_path)
    MOD.root = root
    MOD.loaded = True
    p = _money_system_with_block(root)
    MOD.md_money_system_file = p
    # do not create sloc/yml beforehand — let the method create them
    MOD.md_money_scripted_loc_file = ""
    MOD.md_money_yml_file = ""
    # ensure scan finds nothing
    MOD._scan_md_money_files()
    app = _FakeApp()
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


def test_apply_income_appends_to_existing_tooltip(tmp_path):
    root = str(tmp_path)
    MOD.root = root
    MOD.loaded = True
    p = _money_system_with_block(root)
    MOD.md_money_system_file = p
    sloc = os.path.join(
        root, "common", "scripted_localisation", "money_scripted_localization.txt"
    )
    _write(sloc, "")
    MOD.md_money_scripted_loc_file = sloc
    yml = os.path.join(root, "localisation", "english", "MD_money_l_english.yml")
    _write(yml, 'l_english:\n ADDITIONAL_INCOME_REVENUES_TOOLTIP: "first line"\n')
    MOD.md_money_yml_file = yml
    app = _FakeApp()
    app._apply_md_additional_income("SPIRIT_A", "var_a", "0.1", "tt_a")
    app._apply_md_additional_income("SPIRIT_B", "var_b", "0.2", "tt_b")
    txt = _read(yml)
    assert "[additional_income_summary_SPIRIT_A]" in txt
    assert "[additional_income_summary_SPIRIT_B]" in txt
