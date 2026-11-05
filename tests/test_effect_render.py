import hashlib

import pytest

from hoi4cm.data import EFFECT_DEFS
from hoi4cm.script.effects import _unwrap_scope_body, render_effect
from hoi4cm.script.syntax import match_brace, parse_script


@pytest.mark.parametrize(
    ("effect_type", "expected"),
    [
        (
            "every_state",
            {"type": "infrastructure", "level": "1", "instant_build": "yes"},
        ),
        (
            "random_list",
            {"10": {"add_political_power": "100"}, "25": {"add_stability": "0.05"}},
        ),
        ("while_loop_effect", {"var": "my_var", "value": "1"}),
    ],
)
def test_scope_defaults_preserve_nested_content(effect_type, expected):
    fields = {field[0]: field[2] for field in EFFECT_DEFS[effect_type]["fields"]}
    rendered = render_effect({"type": effect_type, "fields": fields})
    assert match_brace(rendered, rendered.index("{")) == len(rendered) - 1
    body = parse_script(rendered)[effect_type]
    if effect_type == "every_state":
        assert body["limit"] == {"is_controlled_by": "ROOT"}
        assert body["add_building_construction"] == expected
    elif effect_type == "random_list":
        assert body == expected
    else:
        assert body["limit"]["check_variable"]["var"] == "my_var"
        assert body["add_to_variable"] == expected


def test_if_limit_preserves_nested_blocks():
    rendered = render_effect(
        {
            "type": "if",
            "fields": {"limit": "NOT = { tag = GER }", "effect": "foo = yes"},
        }
    )
    assert match_brace(rendered, rendered.index("{")) == len(rendered) - 1
    assert parse_script(rendered)["if"] == {
        "limit": {"NOT": {"tag": "GER"}},
        "foo": "yes",
    }


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            '{ text = "} [ #" # ] }\n nested = { value = yes } }',
            ' text = "} [ #" # ] }\n nested = { value = yes } ',
        ),
        ("[ nested = { value = yes } ]", " nested = { value = yes } "),
        ("{ a = yes } { b = yes }", "{ a = yes } { b = yes }"),
        ("{ a = [ b = yes } ]", "{ a = [ b = yes } ]"),
        ("{ a = yes", "{ a = yes"),
        ("{ a = yes } # trailing comment", "{ a = yes } # trailing comment"),
    ],
)
def test_scope_body_removes_only_a_complete_matching_wrapper(body, expected):
    assert _unwrap_scope_body(body, allow_list=True) == expected


def test_scope_quotes_preserve_apostrophes_and_normalize_legacy_strings():
    rendered = render_effect(
        {
            "type": "if",
            "fields": {"effect": "{ a = '}'\n b = \"owner's {\" # don't }\n }"},
        }
    )
    assert 'a = "}"' in rendered
    assert "b = \"owner's {\" # don't }" in rendered
    assert match_brace(rendered, rendered.index("{")) == len(rendered) - 1
    assert parse_script(rendered)["if"] == {"a": "}", "b": "owner's {"}


def test_scope_preserves_multiline_double_quoted_content():
    rendered = render_effect(
        {"type": "if", "fields": {"effect": "{ text = \"first\n' } '\nlast\" }"}}
    )
    assert 'text = "first\n' in rendered
    assert "' } '" in rendered
    assert 'last"' in rendered
    assert match_brace(rendered, rendered.index("{")) == len(rendered) - 1


def test_all_defined_effect_default_renderings_are_unchanged():
    rendered = []
    for effect_type in sorted(EFFECT_DEFS):
        fields = {
            field[0]: field[2] for field in EFFECT_DEFS[effect_type].get("fields", [])
        }
        rendered.append(
            f"{effect_type}\0{render_effect({'type': effect_type, 'fields': fields})}"
        )

    digest = hashlib.sha256("\0".join(rendered).encode()).hexdigest()
    assert len(rendered) == 641
    assert digest == "911afb6cd202618910bc1bdf8844b6ca2b6377cdd08e132bb004f7d1833ea145"


def test_raw_effect_preserves_lines_with_completion_reward_indent():
    effect = {
        "type": "_raw_block",
        "fields": {"raw": "if = {\n\tlimit = { always = yes }\n\teffect = yes\n}"},
    }

    assert render_effect(effect) == (
        "\t\t\tif = {\n"
        "\t\t\t\tlimit = { always = yes }\n"
        "\t\t\t\teffect = yes\n"
        "\t\t\t}"
    )


def test_unknown_effect_uses_generic_fallback():
    effect = {"type": "custom_unknown", "fields": {"target": "ENG", "value": 2}}

    assert render_effect(effect) == (
        "\t\t\tcustom_unknown = {\n"
        "\t\t\t\ttarget = ENG\n"
        "\t\t\t\tvalue = 2\n"
        "\t\t\t}"
    )
