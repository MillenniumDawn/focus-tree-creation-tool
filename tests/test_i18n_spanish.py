"""Spanish (es) UI locale — issue #24.

``locales/es.json`` must mirror the English locale exactly: same keys, same
named format placeholders with the same multiplicity, and the same literal
brace/script tokens. ``es`` must be selectable as ``Español`` and persist like
the other UI languages, while keeping the Spanish HOI4 localisation target
(``spanish`` / ``l_spanish``) and its generator/discovery behaviour working.
Fixture style mirrors ``test_i18n.py`` (isolated module state + config).
"""

import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from hoi4cm.core import i18n as i18n_mod
from hoi4cm.focus_tree.export_plan import (
    execute_export_plans,
    make_main_export_plan,
)
from hoi4cm.focus_tree.loc import LOC_LANGUAGE_NAMES, LocTarget, build_loc_yml
from hoi4cm.mod import detect_loc_file, find_loc_files
from hoi4cm.models import Focus
from hoi4cm.wizards._generators import (
    build_dyn_mod_output,
    build_national_spirit_output,
    generate_decision_loc_yml,
    generate_event_loc_yml,
)

LOCALE_DIR = Path(__file__).parent.parent / "locales"

# Keys whose values legitimately coincide because they are brand marks,
# script identifiers, or words that are identical in both languages.
_IDENTICAL_KEYS = frozenset(
    {
        "app.brand",
        "app.title.tree",
        "common.browse_symbol",
        "decision.field.priority_raw",
        "decision.solo",
        "dialog.error.title",
        "dialog.mutex.title",
        "event.option.ai_chance",
        "event.section.flags",
        "focus.conditions.flags",
        "focus.conditions.search_filters_label",
        "settings.event_picture_profiles.vanilla_hint",
        "settings.tag",
        "spirit.field.ai_will_do",
        "spirit.field.allowed",
        "spirit.field.available",
        "spirit.field.cancel",
        "spirit.field.on_add",
        "spirit.field.on_remove",
        "spirit.field.rule",
        "spirit.field.visible",
        "status.mod",
        "status.zoom",
        "toolbar.cursor",
        "toolbar.ideas",
        "toolbar.multi",
        "toolbar.mutex",
    }
)

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@pytest.fixture
def restore_i18n_state():
    """Snapshot i18n module state and restore it after the test."""
    saved = (i18n_mod.I18N_LANG, dict(i18n_mod.I18N_STRINGS))
    yield
    i18n_mod.I18N_LANG, i18n_mod.I18N_STRINGS = saved


@pytest.fixture
def fake_config(tmp_path, monkeypatch):
    """Repoint cfg_load/cfg_save to a tmp JSON file (test_i18n.py's shape)."""
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


def _locales():
    english = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
    spanish = json.loads((LOCALE_DIR / "es.json").read_text(encoding="utf-8"))
    return english, spanish


def test_spanish_locale_has_exact_english_key_parity():
    english, spanish = _locales()
    assert set(spanish) == set(english)


def test_spanish_locale_preserves_named_placeholders():
    """Every named {placeholder} survives with identical multiplicity."""
    english, spanish = _locales()

    for key, english_text in english.items():
        assert Counter(_PLACEHOLDER_RE.findall(spanish[key])) == Counter(
            _PLACEHOLDER_RE.findall(english_text)
        ), key


def test_spanish_locale_keeps_literal_brace_tokens():
    """Literal brace groups that are not placeholders must stay verbatim."""
    english, spanish = _locales()

    assert spanish["focus.view_code"] == english["focus.view_code"].replace(
        "View Focus Code", "Ver código del foco"
    )
    assert "{ }" in spanish["focus.view_code"]
    assert (
        "add_dynamic_modifier = { modifier = ... })"
        in spanish["dynamic_modifier.field.modifier_id"]
    )


def test_spanish_locale_is_translated_not_english_copies():
    """Prose values must differ from English; only script terms may coincide."""
    english, spanish = _locales()

    copied = {key for key in english if english[key] == spanish[key]}
    assert copied == _IDENTICAL_KEYS


def test_spanish_locale_values_are_strings():
    _english, spanish = _locales()

    assert all(isinstance(value, str) for value in spanish.values())


def test_spanish_income_tooltip_hint_is_translated():
    _english, spanish = _locales()

    assert spanish["income.hint.tooltip_text"] == (
        "Texto que se muestra en el desglose del tooltip de ingresos adicionales."
    )


def test_spanish_is_registered_as_espanol():
    assert i18n_mod.I18N_LANGS["es"] == "Español"


def test_spanish_is_selectable_and_persisted(restore_i18n_state, fake_config):
    i18n_mod.set_language("es")

    assert i18n_mod.get_language() == "es"
    assert i18n_mod.tr("common.cancel") == "Cancelar"
    assert json.loads(fake_config.read_text()).get("language") == "es"


def test_spanish_strings_interpolate_kwargs(restore_i18n_state):
    i18n_mod._load_i18n("es")

    assert i18n_mod.tr("common.selected_count", count=3) == "3 seleccionado(s)"
    assert i18n_mod.tr("status.zoom", zoom=50) == "Zoom: 50%"
    assert (
        i18n_mod.tr("app.title.tree", tree="SOV")
        == "HOI4 Content Maker  -  SOV  [Wiki Accurate v2]"
    )
    # Literal brace groups still survive a failed format lookup untouched.
    assert i18n_mod.tr("focus.view_code") == "Ver código del foco  { }"


def test_spanish_env_var_selects_language(restore_i18n_state, fake_config, monkeypatch):
    """HOI4CM_LANG outranks the saved config when no argument is forced."""
    fake_config.write_text(json.dumps({"language": "de"}))
    monkeypatch.setenv("HOI4CM_LANG", "es")

    i18n_mod._load_i18n()

    assert i18n_mod.get_language() == "es"
    assert i18n_mod.tr("common.next") == "Siguiente"
    # An explicit argument still wins over the env var.
    i18n_mod._load_i18n("en")
    assert i18n_mod.get_language() == "en"


def test_loc_target_resolves_spanish_header_directory_and_filename():
    for raw in ("spanish", "Spanish", "  SPANISH  "):
        target = LocTarget(raw)

        assert target.language == "spanish"
        assert target.display_name == "Spanish"
        assert target.header() == "l_spanish:"
        assert target.dirname() == "spanish"
        assert target.filename("MD_focus_TST") == "MD_focus_TST_l_spanish.yml"


def test_loc_language_names_offer_spanish():
    assert LOC_LANGUAGE_NAMES["spanish"] == "Spanish"


def test_build_loc_yml_uses_spanish_header(tmp_path):
    focus = Focus(0, 0)
    focus.name = "TST_root"

    text, count = build_loc_yml(None, [focus], "TST", language="spanish")

    assert count == 2
    assert text is not None
    assert text.startswith("l_spanish:\n")
    assert ' TST_root: "Tst Root"\n' in text


def _simple_event(eid, title="Título", desc="Descripción"):
    return SimpleNamespace(
        eid=eid,
        title_text=title,
        desc_text=desc,
        options=[{"name": "OPTA", "text": "Opción A"}],
    )


def test_event_generator_emits_spanish_loc_header():
    output = generate_event_loc_yml([_simple_event("span.1")], loc_language="spanish")

    assert output.startswith("l_spanish:\n")
    assert ' span.1.t: "Título"' in output


def test_decision_generator_emits_spanish_loc_header():
    cats = [{"cat_id": "TST_CAT", "loc_name": "Categoría", "loc_desc": ""}]
    decs = [
        {
            "cat_uid": "c1",
            "dec_id": "TST_DEC",
            "loc_name": "Decisión",
            "loc_desc": "Descripción",
        }
    ]

    output = generate_decision_loc_yml(
        [{"uid": "c1", **cats[0]}], decs, loc_language="spanish"
    )

    assert output.startswith("l_spanish:")
    assert ' TST_CAT: "Categoría"' in output
    assert ' TST_DEC: "Decisión"' in output


def test_dyn_mod_generator_points_at_spanish_loc_path():
    output = build_dyn_mod_output(mod_id="TST_mod", loc_language="spanish")

    assert "localisation/spanish/TAG_l_spanish.yml" in output


def test_national_spirit_generator_points_at_spanish_loc_path():
    output = build_national_spirit_output(mod_id="TST_spirit", loc_language="spanish")

    assert "localisation/spanish/TST_spirit_l_spanish.yml" in output


def _spanish_mod_tree(tmp_path):
    spanish = tmp_path / "localisation" / "spanish" / "MD_focus_TST_l_spanish.yml"
    english = tmp_path / "localisation" / "english" / "MD_focus_TST_l_english.yml"
    stray = tmp_path / "localisation" / "extra" / "old_l_spanish.yml"
    english.parent.mkdir(parents=True)
    spanish.parent.mkdir(parents=True)
    stray.parent.mkdir(parents=True)
    english.write_text("l_english:\n", encoding="utf-8")
    spanish.write_text("l_spanish:\n", encoding="utf-8")
    stray.write_text("l_spanish:\n", encoding="utf-8")
    return spanish, english, stray


def test_find_loc_files_discovers_spanish_directory_first(tmp_path):
    spanish, english, stray = _spanish_mod_tree(tmp_path)

    found = find_loc_files(str(tmp_path), language="spanish")

    assert found == [str(spanish), str(stray)]
    assert str(english) not in found


def test_detect_loc_file_matches_configured_spanish_suffix(tmp_path):
    spanish, english, _stray = _spanish_mod_tree(tmp_path)
    raw = "focus_tree = {\n\tid = TST_focus_tree\n\tcountry = {\n\t\tfactor = 1\n\t}\n}"

    assert detect_loc_file(str(tmp_path), raw, language="spanish") == str(spanish)
    # With the English default the Spanish-named files are not candidates.
    assert detect_loc_file(str(tmp_path), raw) == str(english)


def test_main_export_plan_writes_spanish_localisation(tmp_path):
    focus = Focus(0, 0)
    focus.name = "TST_root"
    loc_path = tmp_path / "MD_focus_TST_l_spanish.yml"
    plan = make_main_export_plan(
        label="Main: TST_focus_tree",
        focus_path=str(tmp_path / "05_TST.txt"),
        loc_path=str(loc_path),
        focuses=[focus],
        tree_info={
            "tree_id": "TST_focus_tree",
            "country_tag": "TST",
            "cfp_x": None,
            "cfp_y": None,
            "country_raw": "",
            "tree_extras": {},
            "shared_focuses": [],
            "joint_focuses": [],
        },
        focus_lookup={focus.id: focus},
        focus_name_lookup={focus.name: focus},
        loc_language="spanish",
    )
    calls = []

    results = execute_export_plans([plan], lambda entries: calls.append(tuple(entries)))

    assert len(results) == 1
    assert results[0].ok
    assert results[0].written_paths == (plan.focus_path, plan.loc_path)
    assert results[0].localisation_added == 2
    loc_text = calls[0][1][1]
    assert loc_text.startswith("l_spanish:\n")
    assert "TST_root" in loc_text
