"""Tests for hoi4cm.focus_tree.loc.build_loc_yml.

Pins the monolith's ``_export`` loc-writing behavior: existing keys are
detected via a ``key: "val"`` / ``key:0 "val"`` regex, a missing file gets an
``l_english:`` header, a section header is written once per country tag (not
duplicated on repeat exports), and existing content is never rewritten —
only appended to.
"""

from types import SimpleNamespace

from hoi4cm.focus_tree.loc import build_loc_yml


def _focus(name, desc=""):
    return SimpleNamespace(name=name, desc=desc)


def test_missing_file_gets_header_and_all_keys():
    focuses = [_focus("TST_alpha")]
    text, count = build_loc_yml(None, focuses, "TST")
    assert count == 2
    assert text.startswith("l_english:\n")
    assert "##########Focuses - TST##########" in text
    assert ' TST_alpha: "Tst Alpha"\n' in text
    assert ' TST_alpha_desc: "Complete the Tst Alpha national focus."\n' in text


def test_desc_falls_back_to_generated_sentence_when_blank():
    focuses = [_focus("TST_alpha", desc="")]
    text, _count = build_loc_yml(None, focuses, "TST")
    assert ' TST_alpha_desc: "Complete the Tst Alpha national focus."\n' in text


def test_desc_uses_focus_desc_when_present():
    focuses = [_focus("TST_alpha", desc="Do the thing.")]
    text, _count = build_loc_yml(None, focuses, "TST")
    assert ' TST_alpha_desc: "Do the thing."\n' in text


def test_existing_file_without_header_appends_and_adds_header():
    existing = 'l_english:\n TST_other: "Something Else"\n'
    focuses = [_focus("TST_alpha")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert count == 2
    assert text.startswith(existing)
    assert "##########Focuses - TST##########" in text
    assert ' TST_alpha: "Tst Alpha"\n' in text


def test_existing_header_is_not_duplicated():
    existing = (
        "l_english:\n"
        " ##########Focuses - TST##########\n"
        ' TST_alpha: "Tst Alpha"\n'
    )
    focuses = [_focus("TST_alpha"), _focus("TST_beta")]
    text, count = build_loc_yml(existing, focuses, "TST")
    # TST_alpha (title) and TST_alpha_desc are still missing? No: TST_alpha
    # key is present, so only the _desc key plus all of TST_beta's keys are new.
    assert count == 3
    assert text.count("##########Focuses - TST##########") == 1


def test_all_keys_already_present_returns_none():
    existing = (
        "l_english:\n"
        ' TST_alpha: "Tst Alpha"\n'
        ' TST_alpha_desc: "Complete the Tst Alpha national focus."\n'
    )
    focuses = [_focus("TST_alpha")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert text is None
    assert count == 0


def test_existing_key_detection_handles_pluralization_suffix():
    # HOI4 loc files sometimes suffix the version number: `key:0 "val"`.
    existing = 'l_english:\n TST_alpha:0 "Tst Alpha"\n'
    focuses = [_focus("TST_alpha")]
    text, count = build_loc_yml(existing, focuses, "TST")
    # The name key is detected as already present; only _desc is new.
    assert count == 1
    assert "TST_alpha_desc" in text


def test_empty_but_existing_file_does_not_get_header_line():
    """A present-but-empty file is appended to, not re-created with a header."""
    focuses = [_focus("TST_alpha")]
    text, _count = build_loc_yml("", focuses, "TST")
    assert not text.startswith("l_english:")
    assert "##########Focuses - TST##########" in text


def test_custom_language_header_for_fresh_file():
    focuses = [_focus("TST_alpha")]
    text, _count = build_loc_yml(None, focuses, "TST", language="french")
    assert text.startswith("l_french:\n")


def test_name_title_cased_with_underscores_replaced():
    focuses = [_focus("TST_some_focus_name")]
    text, _count = build_loc_yml(None, focuses, "TST")
    assert ' TST_some_focus_name: "Tst Some Focus Name"\n' in text
