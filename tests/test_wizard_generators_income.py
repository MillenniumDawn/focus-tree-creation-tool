"""Headless tests for the additional-income wizard's spirit snippet."""

from hoi4cm.wizards._generators import build_income_spirit_snippet


def test_build_income_spirit_snippet_minimal():
    out = build_income_spirit_snippet(
        idea_id="TAG_idea",
        country_tag="TAG",
        variable_name="TAG_money_var",
        tooltip_key="tag_money_tt",
    )
    assert "TAG_idea = {" in out
    assert "name = TAG_idea" in out
    assert "allowed_civil_war = { always = yes }" in out
    assert "picture = GFX_idea_TAG_idea" in out
    assert "NOT = { original_tag = TAG }" in out
    assert "custom_modifier_tooltip = tag_money_tt" in out


def test_build_income_spirit_snippet_emits_loc_hints():
    out = build_income_spirit_snippet(
        idea_id="TAG_idea",
        country_tag="TAG",
        variable_name="TAG_money_var",
        tooltip_key="tag_money_tt",
        spirit_name="My Spirit",
        spirit_desc="My description.",
    )
    assert '# TAG_idea: "My Spirit"' in out
    assert '# TAG_idea_desc: "My description."' in out
    assert '# tag_money_tt: "$$[?TAG_money_var|+3] from §Y$TAG_idea$§!\\n"' in out


def test_build_income_spirit_snippet_escapes_quotes_in_loc_hints():
    out = build_income_spirit_snippet(
        idea_id="TAG_idea",
        country_tag="TAG",
        variable_name="TAG_money_var",
        tooltip_key="tag_money_tt",
        spirit_name='My "Spirit"',
        spirit_desc='Say "hi".',
    )
    assert '# TAG_idea: "My \\"Spirit\\""' in out
    assert '# TAG_idea_desc: "Say \\"hi\\"."' in out
