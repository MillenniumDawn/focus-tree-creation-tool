"""Headless tests for the event-wizard script/loc generators.

The closures inside `open_event_wizard` used to do all of this work, but
that made the script/loc renderers untestable in CI (see issue #51 and
`docs/dev/wizards.md`). After extraction they live as pure module-level
functions in `hoi4cm.wizard._generators`.
"""

from types import SimpleNamespace

import pytest

from hoi4cm.wizards._generators import (
    build_event_scripted_loc_blocks,
    generate_event_loc_yml,
    generate_events_txt,
    render_event_txt,
)


def _make_event(**overrides):
    """Build a minimal duck-typed event data object the renderer accepts."""
    base = dict(
        etype="country_event",
        eid="my_namespace.1",
        title_text="My Event Title",
        desc_text="What is happening in this event.",
        picture="GFX_report_event_generic_handshake",
        major=False,
        fire_once=False,
        triggered=True,
        hidden=False,
        trigger_code="",
        mtth_days="",
        mtth_months="",
        immediate="",
        options=[
            {
                "name": "my_namespace.1.a",
                "text": "Option A",
                "effects": "add_political_power = 50",
                "ai_chance": "75",
            },
        ],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_render_event_txt_basic_emits_headers_and_option():
    out = render_event_txt(_make_event())

    assert out.startswith("country_event = {")
    assert "\tid = my_namespace.1" in out
    assert "\ttitle = my_namespace.1.t" in out
    assert "\tdesc = my_namespace.1.d" in out
    assert "\tpicture = GFX_report_event_generic_handshake" in out
    assert "\tis_triggered_only = yes" in out
    assert "\toption = {" in out
    assert "\t\tname = my_namespace.1.a" in out
    assert "\t\tai_chance = { base = 75 }" in out


def test_render_event_txt_injects_log_line_when_option_has_effects():
    out = render_event_txt(
        _make_event(
            options=[
                {
                    "name": "ns.1.a",
                    "text": "Do thing",
                    "effects": "add_political_power = 10",
                    "ai_chance": "1",
                },
            ],
        )
    )

    assert (
        '\t\tlog = "[GetDateText]: [This.GetName]: ns.1.a executed"' in out
    ), "Missing auto-injected log line for option with effects"


def test_render_event_txt_does_not_inject_log_when_no_effects():
    out = render_event_txt(
        _make_event(
            options=[
                {
                    "name": "ns.1.a",
                    "text": "Nothing",
                    "effects": "",
                    "ai_chance": "1",
                },
            ],
        )
    )

    assert "log = " not in out


def test_render_event_txt_does_not_inject_log_when_user_already_has_one():
    out = render_event_txt(
        _make_event(
            options=[
                {
                    "name": "ns.1.a",
                    "text": "With log",
                    "effects": 'log = "custom"\nadd_political_power = 1',
                    "ai_chance": "1",
                },
            ],
        )
    )

    # Only the user's custom log line; no duplicate.
    assert out.count("log = ") == 1
    assert 'log = "custom"' in out


def test_render_event_txt_emits_mtth_days_only():
    out = render_event_txt(_make_event(mtth_days="30", mtth_months=""))
    assert "\tmean_time_to_happen = {\n\t\tdays = 30\n\t}" in out


def test_render_event_txt_emits_mtth_months_only():
    out = render_event_txt(_make_event(mtth_days="", mtth_months="6"))
    assert "\tmean_time_to_happen = {\n\t\tmonths = 6\n\t}" in out


def test_render_event_txt_emits_both_mtth_units():
    out = render_event_txt(_make_event(mtth_days="30", mtth_months="6"))
    assert "\tmean_time_to_happen = {\n\t\tdays = 30\n\t\tmonths = 6\n\t}" in out


def test_render_event_txt_omits_mtth_when_unset():
    assert "mean_time_to_happen" not in render_event_txt(_make_event())


def test_render_event_txt_emits_major_and_fire_once_and_hidden_flags():
    out = render_event_txt(_make_event(major=True, fire_once=True, hidden=True))
    assert "\tmajor = yes" in out
    assert "\tfire_only_once = yes" in out
    assert "\thidden = yes" in out


def test_render_event_txt_omits_triggered_only_when_false():
    out = render_event_txt(_make_event(triggered=False))
    assert "is_triggered_only" not in out


def test_render_event_txt_emits_immediate_with_leading_blank_line():
    out = render_event_txt(_make_event(immediate="add_stability = 0.05"))
    # Blank line before immediate matches MD event file convention.
    assert "\n\timmediate = {\n\t\tadd_stability = 0.05\n\t}" in out


def test_render_event_txt_skips_blank_immediate():
    out = render_event_txt(_make_event(immediate=""))
    assert "immediate =" not in out


def test_render_event_txt_includes_trigger_block_when_set():
    out = render_event_txt(_make_event(trigger_code="has_war = yes\ndate > 1939.1.1"))
    assert "\ttrigger = {" in out
    assert "\t\thas_war = yes" in out
    assert "\t\tdate > 1939.1.1" in out


def test_generate_events_txt_groups_namespaces():
    e1 = _make_event(eid="alpha.1")
    e2 = _make_event(eid="alpha.2")
    e3 = _make_event(
        eid="beta.1",
        options=[
            {"name": "beta.1.a", "text": "X", "effects": "", "ai_chance": "1"},
        ],
    )
    out = generate_events_txt([e1, e2, e3])

    assert "add_namespace = alpha" in out
    assert "add_namespace = beta" in out
    # Header
    assert out.startswith("# Generated by HOI4 Content Maker")


def test_generate_events_txt_deduplicates_namespace_lines():
    e1 = _make_event(eid="x.1")
    e2 = _make_event(eid="x.2")
    e3 = _make_event(eid="x.3")
    out = generate_events_txt([e1, e2, e3])
    assert out.count("add_namespace = x") == 1


def test_generate_events_txt_empty_returns_empty_string():
    assert generate_events_txt([]) == ""


def test_generate_event_loc_yml_emits_title_desc_and_options():
    e = _make_event(
        eid="ns.1",
        title_text="The Title",
        desc_text="The description.",
        options=[
            {"name": "ns.1.a", "text": "Choice A", "effects": "", "ai_chance": "1"},
            {"name": "ns.1.b", "text": "Choice B", "effects": "", "ai_chance": "1"},
        ],
    )
    out = generate_event_loc_yml([e])

    assert out.startswith("l_english:")
    assert ' ns.1.t: "The Title"' in out
    assert ' ns.1.d: "The description."' in out
    assert ' ns.1.a: "Choice A"' in out
    assert ' ns.1.b: "Choice B"' in out


def test_generate_event_loc_yml_uses_option_name_when_text_missing():
    e = _make_event(
        options=[
            {"name": "ns.1.a", "effects": "", "ai_chance": "1"},
        ],
    )
    out = generate_event_loc_yml([e])
    # Falls back to the option's id when "text" is missing.
    assert ' ns.1.a: "ns.1.a"' in out


def test_generate_event_loc_yml_escapes_quotes_in_values():
    e = _make_event(
        eid="ns.1",
        title_text='The "Title"',
        desc_text="What is happening.",
        options=[
            {"name": "ns.1.a", "text": 'Say "yes"', "effects": "", "ai_chance": "1"},
        ],
    )
    out = generate_event_loc_yml([e])
    assert ' ns.1.t: "The \\"Title\\""' in out
    assert ' ns.1.a: "Say \\"yes\\""' in out


def test_generate_event_loc_yml_empty_returns_empty_string():
    assert generate_event_loc_yml([]) == ""


def test_generate_event_loc_yml_uses_configured_language_header():
    out = generate_event_loc_yml([_make_event()], loc_language="french")

    assert out.startswith("l_french:")


@pytest.mark.parametrize(
    "flag,line",
    [
        ("major", "\tmajor = yes"),
        ("fire_once", "\tfire_only_once = yes"),
        ("hidden", "\thidden = yes"),
        ("triggered", "\tis_triggered_only = yes"),
    ],
)
def test_render_event_txt_emits_each_flag_only_when_set(flag, line):
    assert line in render_event_txt(_make_event(**{flag: True}))
    assert line not in render_event_txt(_make_event(**{flag: False}))


def test_render_event_txt_golden_block():
    # Locks header order, the blank line before `immediate`, and where the
    # injected option log lands; substring assertions can't see any of that.
    out = render_event_txt(
        _make_event(
            eid="ns.1",
            picture="GFX_x",
            fire_once=True,
            trigger_code="has_war = yes",
            mtth_days="30",
            immediate="add_stability = 0.05",
            options=[
                {
                    "name": "ns.1.a",
                    "text": "A",
                    "effects": "add_political_power = 10",
                    "ai_chance": "75",
                },
                {"name": "ns.1.b", "text": "B", "effects": "", "ai_chance": "1"},
            ],
        )
    )
    assert out == "\n".join(
        [
            "country_event = {",
            "\tid = ns.1",
            "\ttitle = ns.1.t",
            "\tdesc = ns.1.d",
            "\tpicture = GFX_x",
            "\tfire_only_once = yes",
            "\tis_triggered_only = yes",
            "\ttrigger = {",
            "\t\thas_war = yes",
            "\t}",
            "\tmean_time_to_happen = {",
            "\t\tdays = 30",
            "\t}",
            "",
            "\timmediate = {",
            "\t\tadd_stability = 0.05",
            "\t}",
            "",
            "\toption = {",
            "\t\tname = ns.1.a",
            '\t\tlog = "[GetDateText]: [This.GetName]: ns.1.a executed"',
            "\t\tadd_political_power = 10",
            "\t\tai_chance = { base = 75 }",
            "\t}",
            "\toption = {",
            "\t\tname = ns.1.b",
            "\t\tai_chance = { base = 1 }",
            "\t}",
            "}",
        ]
    )


def test_render_event_txt_defaults_missing_option_keys():
    out = render_event_txt(_make_event(options=[{}]))
    assert "\t\tname = opt" in out
    assert "\t\tai_chance = { base = 1 }" in out


def test_generate_events_txt_keeps_first_seen_namespace_order():
    events = [
        _make_event(eid="beta.1"),
        _make_event(eid="alpha.1"),
        _make_event(eid="beta.2"),
    ]
    out = generate_events_txt(events)
    assert out.index("add_namespace = beta") < out.index("add_namespace = alpha")


# ── build_event_scripted_loc_blocks (issue #45: the save-to-mod scripted-loc
# step tested `"v_id" in dir()` — always False, since v_id is never bound in
# that closure — then unconditionally called an undefined `_get_output_text`,
# crashing any save with a scripted-loc edit target set) ──────────────────


def test_build_event_scripted_loc_blocks_emits_title_and_desc_per_id():
    blocks = build_event_scripted_loc_blocks(["my_namespace.1"])
    assert blocks == [
        {
            "name": "GET_my_namespace.1_title",
            "texts": [],
            "default": "my_namespace.1.t",
        },
        {"name": "GET_my_namespace.1_desc", "texts": [], "default": "my_namespace.1.d"},
    ]


def test_build_event_scripted_loc_blocks_covers_every_id():
    blocks = build_event_scripted_loc_blocks(["ns.1", "ns.2"])
    names = [b["name"] for b in blocks]
    assert names == [
        "GET_ns.1_title",
        "GET_ns.1_desc",
        "GET_ns.2_title",
        "GET_ns.2_desc",
    ]


def test_build_event_scripted_loc_blocks_skips_blank_ids():
    blocks = build_event_scripted_loc_blocks(["", "  ", "ns.1"])
    assert len(blocks) == 2
    assert blocks[0]["name"] == "GET_ns.1_title"


def test_build_event_scripted_loc_blocks_empty_input_returns_empty_list():
    assert build_event_scripted_loc_blocks([]) == []


def test_build_event_scripted_loc_blocks_accepts_any_iterable():
    """The call site passes a generator expression over `events`, not a list."""
    blocks = build_event_scripted_loc_blocks(ev.eid for ev in [_make_event()])
    assert len(blocks) == 2
