"""Tests for hoi4cm.focus_tree.loc.build_loc_yml."""

from types import SimpleNamespace

from hoi4cm.focus_tree.loc import (
    LOC_LANGUAGE_NAMES,
    LocTarget,
    build_loc_yml,
    hydrate_focus_localization,
)


def _focus(name, desc="", loc_name=""):
    return SimpleNamespace(name=name, desc=desc, loc_name=loc_name)


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


def test_nonblank_localized_name_is_used_for_missing_title_key():
    text, count = build_loc_yml(
        None, [_focus("TST_alpha", loc_name="A Custom Title")], "TST"
    )

    assert count == 2
    assert text is not None
    assert ' TST_alpha: "A Custom Title"\n' in text
    assert ' TST_alpha_desc: "Complete the A Custom Title national focus."\n' in text


def test_blank_localized_name_uses_title_case_fallback():
    text, _count = build_loc_yml(None, [_focus("TST_alpha", loc_name="  ")], "TST")

    assert text is not None
    assert ' TST_alpha: "Tst Alpha"\n' in text


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
        'l_english:\n ##########Focuses - TST##########\n TST_alpha: "Tst Alpha"\n'
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
    focuses = [_focus("TST_alpha", loc_name="Tst Alpha")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert text is None
    assert count == 0


def test_existing_desc_is_rewritten_when_focus_desc_changes():
    existing = (
        'l_english:\n TST_alpha: "Tst Alpha"\n TST_alpha_desc: "Old description."\n'
    )
    focuses = [_focus("TST_alpha", desc="New description.")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert count == 1
    assert ' TST_alpha_desc: "New description."\n' in text
    assert "Old description." not in text
    assert ' TST_alpha: "Tst Alpha"\n' in text


def test_existing_title_is_rewritten_when_localized_name_changes():
    existing = (
        "l_english:\n"
        ' TST_alpha: "Hand-Edited Title"\n'
        ' TST_alpha_desc: "Old description."\n'
    )
    focuses = [_focus("TST_alpha", loc_name="New Title")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert count == 1
    assert text is not None
    assert ' TST_alpha: "New Title"\n' in text
    assert ' TST_alpha_desc: "Old description."\n' in text


def test_blank_localized_name_preserves_existing_title():
    existing = (
        "l_english:\n"
        ' TST_alpha: "Hand-Edited Title"\n'
        ' TST_alpha_desc: "Old description."\n'
    )
    focuses = [_focus("TST_alpha", loc_name="  ")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert text is None
    assert count == 0


def test_blank_desc_never_overwrites_existing_desc():
    existing = (
        "l_english:\n"
        ' TST_alpha: "Tst Alpha"\n'
        ' TST_alpha_desc: "Hand-written description."\n'
    )
    focuses = [_focus("TST_alpha", desc="")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert text is None
    assert count == 0


def test_desc_matching_existing_value_is_not_rewritten():
    existing = (
        'l_english:\n TST_alpha: "Tst Alpha"\n TST_alpha_desc: "Same description."\n'
    )
    focuses = [_focus("TST_alpha", desc="Same description.")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert text is None
    assert count == 0


def test_rewritten_desc_value_with_quote_is_escaped():
    existing = (
        'l_english:\n TST_alpha: "Tst Alpha"\n TST_alpha_desc: "Old description."\n'
    )
    focuses = [_focus("TST_alpha", desc='Say "hello".')]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert count == 1
    assert ' TST_alpha_desc: "Say \\"hello\\"."\n' in text


def test_rewritten_desc_preserves_pluralization_suffix():
    existing = (
        'l_english:\n TST_alpha: "Tst Alpha"\n TST_alpha_desc:0 "Old description."\n'
    )
    focuses = [_focus("TST_alpha", desc="New description.")]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert count == 1
    assert ' TST_alpha_desc:0 "New description."\n' in text


def test_rewrite_and_add_combine_in_one_pass():
    existing = (
        'l_english:\n TST_alpha: "Tst Alpha"\n TST_alpha_desc: "Old description."\n'
    )
    focuses = [
        _focus("TST_alpha", desc="New description."),
        _focus("TST_beta"),
    ]
    text, count = build_loc_yml(existing, focuses, "TST")
    assert count == 3
    assert ' TST_alpha_desc: "New description."\n' in text
    assert ' TST_beta: "Tst Beta"\n' in text
    assert ' TST_beta_desc: "Complete the Tst Beta national focus."\n' in text


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


def test_loc_target_covers_every_supported_hoi4_language():
    assert tuple(LOC_LANGUAGE_NAMES) == (
        "english",
        "french",
        "german",
        "spanish",
        "braz_por",
        "polish",
        "russian",
        "japanese",
        "simp_chinese",
    )


def test_loc_target_resolves_header_directory_and_filename():
    target = LocTarget("french")

    assert target.header() == "l_french:"
    assert target.dirname() == "french"
    assert target.filename("TAG_focus") == "TAG_focus_l_french.yml"


def test_loc_target_uses_explicit_brazilian_portuguese_mapping():
    target = LocTarget("braz_por")

    assert target.header() == "l_braz_por:"
    assert target.dirname() == "braz_por"
    assert target.filename("TAG") == "TAG_l_braz_por.yml"


def test_loc_target_invalid_language_falls_back_to_english():
    target = LocTarget("not-a-language")

    assert target.language == "english"
    assert target.header() == "l_english:"


def test_name_title_cased_with_underscores_replaced():
    focuses = [_focus("TST_some_focus_name")]
    text, _count = build_loc_yml(None, focuses, "TST")
    assert ' TST_some_focus_name: "Tst Some Focus Name"\n' in text


def test_values_are_escaped():
    text, _count = build_loc_yml(None, [_focus("TST_alpha", 'Say "hello"\\now')], "TST")
    assert ' TST_alpha_desc: "Say \\"hello\\"\\\\now"\n' in text


def test_hydrate_focus_localization_decodes_exported_escapes():
    focus = _focus("TST_alpha", desc="old", loc_name="old title")
    text = (
        "l_english:\n"
        ' TST_alpha: "A \\"quoted\\" title"\n'
        ' TST_alpha_desc: "Say \\"hello\\"\\\\now"\n'
    )

    hydrate_focus_localization(text, [focus])

    assert focus.loc_name == 'A "quoted" title'
    assert focus.desc == 'Say "hello"\\now'


def test_hydrate_focus_localization_leaves_missing_values_untouched():
    focus = _focus("TST_alpha", desc="existing", loc_name="Existing")

    hydrate_focus_localization('l_english:\n TST_other: "Other"\n', [focus])

    assert focus.loc_name == "Existing"
    assert focus.desc == "existing"


def test_existing_content_without_newline_gets_separator():
    text, _count = build_loc_yml("l_english:", [_focus("TST_alpha")], "TST")
    assert text.startswith("l_english:\n")
