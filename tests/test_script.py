"""Tests for hoi4cm.script marshalling helpers."""

from hoi4cm.mod.workspace_files import WorkspaceFiles
from hoi4cm.script import append_scripted_loc, dict_to_raw, normalize_effect_fields


def test_dict_to_raw_handles_bools_and_nested_dicts():
    d = {
        "visible": True,
        "hidden": False,
        "cost": 10,
        "completion_reward": {
            "add_political_power": 100,
            "add_ideas": ["idea_one", "idea_two"],
        },
    }
    raw = dict_to_raw(d)
    assert "\tvisible = yes" in raw
    assert "\thidden = no" in raw
    assert "\tcompletion_reward = {" in raw
    assert "\t\tadd_political_power = 100" in raw
    assert "\t\tadd_ideas = idea_one" in raw
    assert "\t\tadd_ideas = idea_two" in raw


def test_dict_to_raw_skips_underscore_keys():
    d = {"keep": 1, "_internal": 2}
    raw = dict_to_raw(d)
    assert "keep = 1" in raw
    assert "_internal" not in raw


def test_normalize_effect_fields_flat_value():
    defs = {"add_political_power": {"fields": [("amount", "entry", "100", "")]}}
    assert normalize_effect_fields("add_political_power", 50, defs) == {"amount": "50"}


def test_normalize_effect_fields_dict_with_known_fields():
    defs = {
        "add_popularity": {
            "fields": [
                ("ideology", "dropdown", "democratic", ""),
                ("popularity", "entry", "0.05", ""),
            ]
        }
    }
    raw = {"ideology": "fascism", "popularity": "0.1"}
    assert normalize_effect_fields("add_popularity", raw, defs) == {
        "ideology": "fascism",
        "popularity": "0.1",
    }


def test_normalize_effect_fields_add_to_variable():
    defs = {
        "add_to_variable": {
            "fields": [("var", "entry", "x", ""), ("value", "entry", "0", "")]
        }
    }
    raw = {"TAG_my_var": "0.05", "tooltip": "stat_tt"}
    assert normalize_effect_fields("add_to_variable", raw, defs) == {
        "var": "TAG_my_var",
        "value": "0.05",
        "tooltip": "stat_tt",
    }


def test_normalize_effect_fields_custom_effect_tooltip_block():
    defs = {"custom_effect_tooltip": {"fields": []}}
    raw = {"localization_key": "my_tt", "MODIFIER": "TAG_mod"}
    assert normalize_effect_fields("custom_effect_tooltip", raw, defs) == {
        "_block_form": "1",
        "localization_key": "my_tt",
        "MODIFIER": "TAG_mod",
    }


def test_normalize_effect_fields_unknown_type_returns_raw():
    defs = {}
    assert normalize_effect_fields("unknown_thing", "value", defs) == {"raw": "value"}


def test_append_scripted_loc_writes_block(tmp_path):
    sloc = tmp_path / "test_scripted_loc.txt"
    saved = []
    errs = []
    blocks = [
        {
            "name": "GET_TAG_greeting",
            "texts": [("has_country_flag = hello", "TAG_hello")],
            "default": "TAG_default_greeting",
        }
    ]
    append_scripted_loc(str(sloc), blocks, saved, errs)
    assert not errs
    assert len(saved) == 1
    text = sloc.read_text(encoding="utf-8")
    assert "defined_text = {" in text
    assert "name = GET_TAG_greeting" in text
    assert "localization_key = TAG_hello" in text
    assert "localization_key = TAG_default_greeting" in text


def test_append_scripted_loc_skips_existing_name(tmp_path):
    sloc = tmp_path / "test_scripted_loc.txt"
    sloc.write_text(
        "defined_text = {\n\tname = GET_TAG_greeting\n}\n",
        encoding="utf-8",
    )
    saved = []
    errs = []
    blocks = [{"name": "GET_TAG_greeting", "texts": [], "default": "x"}]
    append_scripted_loc(str(sloc), blocks, saved, errs)
    assert not errs
    assert saved == []  # nothing added


def test_append_scripted_loc_preserves_existing_content(tmp_path):
    sloc = tmp_path / "test_scripted_loc.txt"
    sloc.write_text("defined_text = {\n\tname = OLD\n}\n", encoding="utf-8")
    saved = []
    errs = []
    append_scripted_loc(str(sloc), [{"name": "NEW", "texts": []}], saved, errs)
    assert not errs
    assert len(saved) == 1
    text = sloc.read_text(encoding="utf-8")
    assert "name = OLD" in text
    assert "name = NEW" in text


def test_append_scripted_loc_uses_workspace_files(tmp_path, monkeypatch):
    sloc = tmp_path / "test_scripted_loc.txt"
    sloc.write_text("existing\n", encoding="utf-8")
    calls = []

    def capture(self, path, text, *, encoding):
        calls.append((str(path), text, encoding))

    monkeypatch.setattr(WorkspaceFiles, "append_text", capture)
    saved = []
    errs = []
    append_scripted_loc(str(sloc), [{"name": "NEW", "texts": []}], saved, errs)
    assert not errs
    assert len(calls) == 1
    path, text, encoding = calls[0]
    assert path == str(sloc)
    assert encoding == "utf-8"
    assert "name = NEW" in text
    assert sloc.read_text(encoding="utf-8") == "existing\n"


def test_append_scripted_loc_reports_errors(tmp_path, monkeypatch):
    sloc = tmp_path / "file.txt"
    sloc.write_text("old\n", encoding="utf-8")
    saved = []
    errs = []

    def boom(self, path, text, *, encoding):
        raise OSError("permission denied")

    monkeypatch.setattr(WorkspaceFiles, "append_text", boom)
    append_scripted_loc(str(sloc), [{"name": "x", "texts": []}], saved, errs)
    assert errs
    assert "Scripted Loc" in errs[0]
    assert sloc.read_text(encoding="utf-8") == "old\n"
