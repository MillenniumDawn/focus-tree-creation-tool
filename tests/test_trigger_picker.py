"""Snippet rendering for the shared trigger picker."""

from hoi4cm.wizards._shared import render_script_snippet


def test_render_trigger_snippets_without_tk():
    from hoi4cm.data import TRIGGER_DEFS

    assert render_script_snippet(
        "always", TRIGGER_DEFS["always"], {}, is_trigger=True
    ) == ("\talways = yes\n")
    assert (
        render_script_snippet(
            "has_country_flag",
            TRIGGER_DEFS["has_country_flag"],
            {"flag": "my_flag"},
            is_trigger=True,
        )
        == "\thas_country_flag = my_flag\n"
    )
    assert (
        render_script_snippet(
            "has_war_support",
            TRIGGER_DEFS["has_war_support"],
            {"amount": "> 0.5"},
            is_trigger=True,
        )
        == "\thas_war_support > 0.5\n"
    )
    assert (
        render_script_snippet(
            "AND", TRIGGER_DEFS["AND"], {"conditions": "always = yes"}, is_trigger=True
        )
        == "\tAND = {\n\t\talways = yes\n\t}\n"
    )
