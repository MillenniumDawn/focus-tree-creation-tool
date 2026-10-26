"""French (fr) UI locale — issue #22.

``locales/fr.json`` keeps the English locale's literal brace/script tokens and
translates its prose. Key and placeholder parity for every locale is already
enforced generically by ``test_i18n_keys.py`` (the ``LOCALE_PATHS`` glob picks
up ``fr.json``), so this module only covers what is French-specific: token
parity, prose-not-copy, and the French selection/export seams (``french`` ->
``l_french``) through the focus exporter and the wizard generators.

The translation was produced with machine assistance and has not yet been
reviewed by a native French speaker; it is still fully translated (no English
copies beyond brand marks, script identifiers, and words identical in French).
Fixture style mirrors ``test_i18n.py`` (isolated module state + config).
"""

import json
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
        "common.description_no_colon",
        "decision.field.description_loc",
        "decision.field.priority_raw",
        "decision.section.options",
        "decision.solo",
        "dialog.export.title",
        "dialog.import.title",
        "dialog.mutex.title",
        "dialog.position.title",
        "dynamic_modifier.change.description",
        "event.dialog.options.title",
        "event.option.ai_chance",
        "event.option.header",
        "event.section.flags",
        "event.section.options",
        "event.section.type",
        "focus.conditions.bypass",
        "focus.conditions.cancel",
        "focus.conditions.flags",
        "focus.conditions.search_filters_label",
        "focus.prereq.group_separator",
        "gfx.images_count",
        "load_all.column.type",
        "load_all.type.joint",
        "settings.event_picture_profiles.vanilla_hint",
        "spirit.change.description",
        "spirit.field.ai_will_do",
        "spirit.field.allowed",
        "spirit.field.available",
        "spirit.field.cancel",
        "spirit.field.on_add",
        "spirit.field.on_remove",
        "spirit.field.rule",
        "spirit.field.visible",
        "spirit.section.localisation",
        "status.mod",
        "status.zoom",
        "tab.code",
        "tab.conditions",
        "toolbar.add_focus",
        "toolbar.dyn_mod",
        "toolbar.joint",
        "toolbar.multi",
        "toolbar.mutex",
        "undo.action",
        "undo.bulk_rename",
        "validation.col_code",
        "validation.col_focus",
        "validation.col_message",
        "wizard.character.portrait",
    }
)


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
    french = json.loads((LOCALE_DIR / "fr.json").read_text(encoding="utf-8"))
    english.pop("_meta")
    french.pop("_meta")
    return english, french


def test_french_locale_keeps_literal_brace_tokens():
    """Literal brace groups that are not placeholders must stay verbatim."""
    english, french = _locales()

    assert french["focus.view_code"] == english["focus.view_code"].replace(
        "View Focus Code", "Voir le code du focus"
    )
    assert "{ }" in french["focus.view_code"]
    assert (
        "add_dynamic_modifier = { modifier = ... })"
        in french["dynamic_modifier.field.modifier_id"]
    )


def test_french_locale_is_translated_not_english_copies():
    """Prose values must differ from English; only script terms may coincide."""
    english, french = _locales()

    copied = {key for key in english if english[key] == french[key]}
    assert copied == _IDENTICAL_KEYS


def test_french_locale_values_are_strings():
    _english, french = _locales()

    assert all(isinstance(value, str) for value in french.values())


def test_french_meta_declares_display_name_and_review_status():
    meta = json.loads((LOCALE_DIR / "fr.json").read_text(encoding="utf-8"))["_meta"]

    assert meta["display_name"] == "Français"
    # The translation is machine-assisted until a native review lands.
    assert "réviser" in meta["note"].lower()


def test_french_is_registered_as_francais():
    assert i18n_mod.I18N_LANGS["fr"] == "Français"


def test_french_is_selectable_and_persisted(restore_i18n_state, fake_config):
    i18n_mod.set_language("fr")

    assert i18n_mod.get_language() == "fr"
    assert i18n_mod.tr("common.cancel") == "Annuler"
    assert json.loads(fake_config.read_text()).get("language") == "fr"


def test_french_strings_interpolate_kwargs(restore_i18n_state):
    i18n_mod._load_i18n("fr")

    assert i18n_mod.tr("common.selected_count", count=3) == "3 sélectionné(s)"
    assert i18n_mod.tr("mod.loading.step", step=2, total=5, label="gfx") == (
        "Étape 2/5 : gfx"
    )
    assert (
        i18n_mod.tr("app.title.tree", tree="SOV")
        == "HOI4 Content Maker  -  SOV  [Wiki Accurate v2]"
    )
    # Literal brace groups still survive a failed format lookup untouched.
    assert i18n_mod.tr("focus.view_code") == "Voir le code du focus  { }"


def test_french_env_var_selects_language(restore_i18n_state, fake_config, monkeypatch):
    """HOI4CM_LANG outranks the saved config when no argument is forced."""
    fake_config.write_text(json.dumps({"language": "de"}))
    monkeypatch.setenv("HOI4CM_LANG", "fr")

    i18n_mod._load_i18n()

    assert i18n_mod.get_language() == "fr"
    assert i18n_mod.tr("common.next") == "Suivant"
    # An explicit argument still wins over the env var.
    i18n_mod._load_i18n("en")
    assert i18n_mod.get_language() == "en"


def test_loc_target_resolves_french_header_directory_and_filename():
    for raw in ("french", "French", "  FRENCH  "):
        target = LocTarget(raw)

        assert target.language == "french"
        assert target.display_name == "French"
        assert target.header() == "l_french:"
        assert target.dirname() == "french"
        assert target.filename("MD_focus_TST") == "MD_focus_TST_l_french.yml"


def test_loc_language_names_offer_french():
    assert LOC_LANGUAGE_NAMES["french"] == "French"


def test_build_loc_yml_uses_french_header(tmp_path):
    focus = Focus(id=1, x=0, y=0)
    focus.name = "TST_root"

    text, count = build_loc_yml(None, [focus], "TST", language="french")

    assert count == 2
    assert text is not None
    assert text.startswith("l_french:\n")
    assert ' TST_root: "Tst Root"\n' in text


def _simple_event(eid, title="Titre", desc="Description"):
    return SimpleNamespace(
        eid=eid,
        title_text=title,
        desc_text=desc,
        options=[{"name": "OPTA", "text": "Option A"}],
    )


def test_event_generator_emits_french_loc_header():
    output = generate_event_loc_yml([_simple_event("fr.1")], loc_language="french")

    assert output.startswith("l_french:\n")
    assert ' fr.1.t: "Titre"' in output


def test_decision_generator_emits_french_loc_header():
    cats = [{"cat_id": "TST_CAT", "loc_name": "Catégorie", "loc_desc": ""}]
    decs = [
        {
            "cat_uid": "c1",
            "dec_id": "TST_DEC",
            "loc_name": "Décision",
            "loc_desc": "Description",
        }
    ]

    output = generate_decision_loc_yml(
        [{"uid": "c1", **cats[0]}], decs, loc_language="french"
    )

    assert output.startswith("l_french:")
    assert ' TST_CAT: "Catégorie"' in output
    assert ' TST_DEC: "Décision"' in output


def test_dyn_mod_generator_points_at_french_loc_path():
    output = build_dyn_mod_output(mod_id="TST_mod", loc_language="french")

    assert "localisation/french/TAG_l_french.yml" in output


def test_national_spirit_generator_points_at_french_loc_path():
    output = build_national_spirit_output(mod_id="TST_spirit", loc_language="french")

    assert "localisation/french/TST_spirit_l_french.yml" in output


def _french_mod_tree(tmp_path):
    french = tmp_path / "localisation" / "french" / "MD_focus_TST_l_french.yml"
    english = tmp_path / "localisation" / "english" / "MD_focus_TST_l_english.yml"
    stray = tmp_path / "localisation" / "extra" / "old_l_french.yml"
    english.parent.mkdir(parents=True)
    french.parent.mkdir(parents=True)
    stray.parent.mkdir(parents=True)
    english.write_text("l_english:\n", encoding="utf-8")
    french.write_text("l_french:\n", encoding="utf-8")
    stray.write_text("l_french:\n", encoding="utf-8")
    return french, english, stray


def test_find_loc_files_discovers_french_directory_first(tmp_path):
    french, english, stray = _french_mod_tree(tmp_path)

    found = find_loc_files(str(tmp_path), language="french")

    assert found == [str(french), str(stray)]
    assert str(english) not in found


def test_detect_loc_file_matches_configured_french_suffix(tmp_path):
    french, english, _stray = _french_mod_tree(tmp_path)
    raw = "focus_tree = {\n\tid = TST_focus_tree\n\tcountry = {\n\t\tfactor = 1\n\t}\n}"

    assert detect_loc_file(str(tmp_path), raw, language="french") == str(french)
    # With the English default the French-named files are not candidates.
    assert detect_loc_file(str(tmp_path), raw) == str(english)


def test_main_export_plan_writes_french_localisation(tmp_path):
    focus = Focus(id=2, x=0, y=0)
    focus.name = "TST_root"
    loc_path = tmp_path / "MD_focus_TST_l_french.yml"
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
        loc_language="french",
    )
    calls = []

    results = execute_export_plans([plan], lambda entries: calls.append(tuple(entries)))

    assert len(results) == 1
    assert results[0].ok
    assert results[0].written_paths == (plan.focus_path, plan.loc_path)
    assert results[0].localisation_added == 2
    loc_text = calls[0][1][1]
    assert loc_text.startswith("l_french:\n")
    assert "TST_root" in loc_text
