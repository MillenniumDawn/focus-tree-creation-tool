"""Headless tests for wizard collect_*_state helpers (issue #62).

Each wizard closure previously read Tk ``StringVar``/``Text`` widgets
inline and delegated to a generator.  Now the reads live in a small
``collect_*_state`` that takes duck-typed ``.get()`` objects, so the
seam is testable without a display.  A rename of an ``_evars`` key or
a drift in the fallback now fails here instead of silently shipping
wrong script.
"""

from types import SimpleNamespace

from hoi4cm.wizards._generators import (
    build_dyn_mod_output,
    build_income_spirit_snippet,
    build_national_spirit_output,
    generate_decision_block,
)
from hoi4cm.wizards.additional_income import collect_additional_income_state
from hoi4cm.wizards.decision import collect_decision_state
from hoi4cm.wizards.dyn_mod import collect_dyn_mod_state
from hoi4cm.wizards.event import collect_event_state
from hoi4cm.wizards.national_spirit import collect_national_spirit_state


class _FakeVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):  # pragma: no cover - not used in tests
        self._value = value


class _FakeText:
    def __init__(self, text):
        self._text = text

    def get(self, *args, **kwargs):
        return self._text


class _BadVar:
    def get(self):
        raise RuntimeError("boom")


# ── decision ──────────────────────────────────────────────────────────


def test_collect_decision_state_from_vars():
    evars = {"targeted": _FakeVar("state"), "cost_type": _FakeVar("custom")}
    assert collect_decision_state(evars) == {"targeted": "state", "cost_type": "custom"}


def test_collect_decision_state_falls_back_to_dec():
    evars = {}
    dec = {"targeted": "country", "cost_type": "custom"}
    assert collect_decision_state(evars, dec) == {
        "targeted": "country",
        "cost_type": "custom",
    }


def test_collect_decision_state_literal_defaults_when_no_dec():
    assert collect_decision_state({}) == {"targeted": "none", "cost_type": "pp"}
    assert collect_decision_state({}, None) == {"targeted": "none", "cost_type": "pp"}


def test_collect_decision_state_var_wins_over_dec():
    evars = {"targeted": _FakeVar("state")}
    dec = {"targeted": "country", "cost_type": "pp"}
    out = collect_decision_state(evars, dec)
    assert out["targeted"] == "state"
    assert out["cost_type"] == "pp"


def test_collect_decision_state_bad_var_falls_back():
    evars = {"targeted": _BadVar(), "cost_type": _BadVar()}
    dec = {"targeted": "country"}
    out = collect_decision_state(evars, dec)
    assert out["targeted"] == "country"
    assert out["cost_type"] == "pp"


def test_collect_decision_state_renamed_key_uses_fallback():
    # Simulate a rename of _evars["targeted"] -> typo; old code would silently
    # render untargeted.  The helper must fall through to dec/default.
    evars = {"targeted_typo": _FakeVar("state"), "cost_type": _FakeVar("custom")}
    dec = {"targeted": "country", "cost_type": "pp"}
    out = collect_decision_state(evars, dec)
    assert out["targeted"] == "country"
    assert out["cost_type"] == "custom"


def test_collect_decision_state_into_generator_targeted():
    # Seam proof: what the closure hands over actually changes the rendered block.
    base = {
        "uid": "dec-1",
        "cat_uid": "cat-1",
        "dec_id": "TAG_decision",
        "loc_name": "My Decision",
        "loc_desc": "",
        "icon": "",
        "allowed": "",
        "visible": "",
        "available": "",
        "cost_type": "pp",
        "cost": "25",
        "custom_cost_trigger": "",
        "custom_cost_text": "",
        "ai_hint_pp_cost": "",
        "cost_var": "",
        "cost_amount": "",
        "days_remove": "",
        "days_re_enable": "",
        "fire_only_once": False,
        "fixed_random_seed": True,
        "is_mission": False,
        "mission_timeout": "100",
        "selectable_mission": False,
        "is_good": False,
        "activation": "",
        "highlight_states": "",
        "on_map_mode": "map_and_decisions_view",
        "state_target_scope": "any",
        "target_root_trigger": "",
        "target_trigger": "",
        "targets": "",
        "targets_dynamic": False,
        "target_non_existing": False,
        "target_array": "",
        "modifier": "",
        "complete_effect": "",
        "timeout_effect": "",
        "remove_effect": "",
        "cancel_trigger": "",
        "cancel_effect": "",
        "cancel_if_not_visible": False,
        "remove_trigger": "",
        "ai_will_do": "",
        "priority": "1",
        "war_target_complete": False,
        "war_target_remove": False,
        "war_complete_tag": "",
        "war_remove_tag": "",
    }
    untargeted = generate_decision_block(base, **collect_decision_state({}))
    assert "state_target" not in untargeted
    targeted = generate_decision_block(
        base, **collect_decision_state({"targeted": _FakeVar("state")})
    )
    assert "state_target = yes" in targeted


# ── national spirit ───────────────────────────────────────────────────


def test_collect_national_spirit_state_maps_scalars_and_text():
    svars = {
        "mod_id": _FakeVar("TAG_s"),
        "name_key": _FakeVar("TAG_s_name"),
        "picture": _FakeVar("GFX_idea_TAG_s"),
        "slot": _FakeVar("country"),
        "cost": _FakeVar("50"),
        "removal": _FakeVar("10"),
        "loc_name": _FakeVar("My Spirit"),
        "loc_desc": _FakeVar("Desc"),
        "ai": _FakeVar("5"),
    }
    text = {
        "allowed": _FakeText("has_war = yes"),
        "available": _FakeText("threat > 0.5"),
        "cancel": _FakeText(""),
        "visible": _FakeText(""),
        "on_add": _FakeText("add_stability = 0.1"),
        "on_remove": _FakeText(""),
        "rule": _FakeText(""),
        "extra": _FakeText("stability_factor = 0.05"),
    }
    state = collect_national_spirit_state(
        svars, text, [{"key": "war_support_factor", "value": "0.1"}]
    )
    assert state["mod_id"] == "TAG_s"
    assert state["allowed"] == "has_war = yes"
    assert state["available"] == "threat > 0.5"
    assert state["on_add"] == "add_stability = 0.1"
    assert state["extra_modifiers"] == "stability_factor = 0.05"
    assert state["modifiers"] == [{"key": "war_support_factor", "value": "0.1"}]
    out = build_national_spirit_output(**state)
    assert "cost = 50" in out
    assert "removal_cost = 10" in out
    assert "allowed = {" in out
    assert "stability_factor = 0.05" in out


def test_collect_national_spirit_state_missing_widgets_defaults():
    state = collect_national_spirit_state({}, {}, None)
    assert state["mod_id"] == ""
    assert state["allowed"] == ""
    assert state["modifiers"] == []
    # Still renders with defaults (TAG_my_spirit fallback in generator)
    out = build_national_spirit_output(**state)
    assert "TAG_my_spirit" in out


def test_collect_national_spirit_state_modifiers_copied():
    mods = [{"key": "k", "value": "1"}]
    state = collect_national_spirit_state({}, {}, mods)
    mods.append({"key": "k2", "value": "2"})
    assert len(state["modifiers"]) == 1


def test_collect_national_spirit_state_text_stripped():
    text = {"allowed": _FakeText("  has_war = yes  \n")}
    state = collect_national_spirit_state({}, text, [])
    assert state["allowed"] == "has_war = yes"


# ── dynamic modifier ──────────────────────────────────────────────────


def test_collect_dyn_mod_state_maps_all_fields():
    svars = {
        "mod_id": _FakeVar("TAG_my_dynamic_modifier"),
        "scope": _FakeVar("state"),
        "icon": _FakeVar("GFX_idea_test"),
        "loc_name": _FakeVar("My Mod"),
        "loc_desc": _FakeVar("Desc"),
    }
    text = {
        "enable": _FakeText("has_war = yes"),
        "mods": _FakeText("stability_factor = my_var"),
        "const": _FakeText("war_support_factor = 0.1"),
    }
    state = collect_dyn_mod_state(svars, text)
    assert state["scope"] == "state"
    assert state["enable"] == "has_war = yes"
    out = build_dyn_mod_output(**state)
    assert "scope = state" in out
    assert "icon = GFX_idea_test" in out
    assert "stability_factor = my_var" in out
    assert "war_support_factor = 0.1" in out


def test_collect_dyn_mod_state_defaults():
    state = collect_dyn_mod_state({}, {})
    assert state["mod_id"] == ""
    assert state["scope"] == "country"
    assert state["enable"] == ""


# ── additional income ─────────────────────────────────────────────────


def test_collect_additional_income_state_normalises():
    svars = {
        "idea_id": _FakeVar(" HKG_bonus "),
        "country_tag": _FakeVar(" hkg "),
        "variable_name": _FakeVar(" HKG_trade_income_gain "),
        "amount": _FakeVar(" 0.05 "),
        "tooltip_key": _FakeVar(" HKG_trade_income_TT "),
        "spirit_name": _FakeVar(" Free Trade "),
        "spirit_desc": _FakeVar(" Desc "),
        "tooltip_text": _FakeVar(" +5% "),
        "mode": _FakeVar("also_spirit"),
        "formula_type": _FakeVar("gdp_pct"),
    }
    state = collect_additional_income_state(svars)
    assert state["idea_id"] == "HKG_bonus"
    assert state["country_tag"] == "HKG"
    assert state["variable_name"] == "HKG_trade_income_gain"
    assert state["mode"] == "also_spirit"
    assert state["formula_type"] == "gdp_pct"
    snippet = build_income_spirit_snippet(
        idea_id=state["idea_id"],
        country_tag=state["country_tag"],
        variable_name=state["variable_name"],
        tooltip_key=state["tooltip_key"],
        spirit_name=state["spirit_name"],
        spirit_desc=state["spirit_desc"],
    )
    assert "HKG_bonus = {" in snippet
    assert "original_tag = HKG" in snippet
    assert "HKG_trade_income_TT" in snippet


def test_collect_additional_income_state_defaults():
    state = collect_additional_income_state({})
    assert state["mode"] == "wire_only"
    assert state["formula_type"] == "fixed"
    assert state["country_tag"] == ""


# ── event ─────────────────────────────────────────────────────────────


def test_collect_event_state_copies_and_handles_none():
    assert collect_event_state(None) == []
    evs = [SimpleNamespace(eid="a.1"), SimpleNamespace(eid="a.2")]
    snap = collect_event_state(evs)
    assert snap == evs
    assert snap is not evs
    evs.append(SimpleNamespace(eid="a.3"))
    assert len(snap) == 2


def test_collect_event_state_into_generators():
    from hoi4cm.wizards._generators import generate_events_txt

    ev = SimpleNamespace(
        etype="country_event",
        eid="test.1",
        title_text="T",
        desc_text="D",
        picture="GFX_report_event_generic_handshake",
        major=False,
        fire_once=False,
        triggered=False,
        hidden=False,
        trigger_code="",
        mtth_days="",
        mtth_months="",
        immediate="",
        options=[{"name": "test.1.a", "text": "OK", "effects": "", "ai_chance": "1"}],
    )
    snap = collect_event_state([ev])
    out = generate_events_txt(snap)
    assert "id = test.1" in out
    assert 'test.1.t: "T"' not in out  # txt file, not loc


def test_collect_decision_state_both_defaults_seam():
    # Replicates the drift the issue flagged: _gen_decision_txt fell back to
    # dec values while _gen_decisions_file fell back to literals. Now both
    # go through the same helper, so the file-level call with no dec matches
    # the single-decision call with an empty dec.
    assert collect_decision_state({}) == collect_decision_state({}, {})


# ── edge / contract ─────────────────────────────────────────────────


def test_collect_decision_state_handles_non_string_and_empty():
    # Non-string .get() is coerced via str(); empty string is preserved
    # (generator treats "" as not-None, so this documents the current contract).
    assert collect_decision_state({"targeted": _FakeVar(123)})["targeted"] == "123"
    assert collect_decision_state({"targeted": _FakeVar("")})["targeted"] == ""
    # evars not a dict -> literal fallback, dec not a dict -> literal fallback
    assert collect_decision_state(None) == {"targeted": "none", "cost_type": "pp"}
    assert collect_decision_state({}, dec="not-a-dict") == {
        "targeted": "none",
        "cost_type": "pp",
    }
    # var without .get falls through
    assert (
        collect_decision_state({"targeted": object()}, {"targeted": "country"})[
            "targeted"
        ]
        == "country"
    )


def test_collect_decision_state_cost_type_into_generator():
    base = {
        "uid": "dec-1",
        "cat_uid": "cat-1",
        "dec_id": "TAG_decision",
        "loc_name": "My Decision",
        "loc_desc": "",
        "icon": "",
        "allowed": "",
        "visible": "",
        "available": "",
        "cost_type": "pp",
        "cost": "25",
        "custom_cost_trigger": "has_dlc = 1",
        "custom_cost_text": "CUSTOM",
        "ai_hint_pp_cost": "10",
        "cost_var": "",
        "cost_amount": "",
        "days_remove": "",
        "days_re_enable": "",
        "fire_only_once": False,
        "fixed_random_seed": True,
        "is_mission": False,
        "mission_timeout": "100",
        "selectable_mission": False,
        "is_good": False,
        "activation": "",
        "highlight_states": "",
        "on_map_mode": "map_and_decisions_view",
        "state_target_scope": "any",
        "target_root_trigger": "",
        "target_trigger": "",
        "targets": "",
        "targets_dynamic": False,
        "target_non_existing": False,
        "target_array": "",
        "modifier": "",
        "complete_effect": "",
        "timeout_effect": "",
        "remove_effect": "",
        "cancel_trigger": "",
        "cancel_effect": "",
        "cancel_if_not_visible": False,
        "remove_trigger": "",
        "ai_will_do": "",
        "priority": "1",
        "war_target_complete": False,
        "war_target_remove": False,
        "war_complete_tag": "",
        "war_remove_tag": "",
    }
    pp = generate_decision_block(
        base, **collect_decision_state({"cost_type": _FakeVar("pp")})
    )
    assert "cost = 25" in pp
    assert "custom_cost_text" not in pp
    custom = generate_decision_block(
        base, **collect_decision_state({"cost_type": _FakeVar("custom")})
    )
    assert "custom_cost_text = CUSTOM" in custom
    assert "custom_cost_trigger" in custom


def test_collect_national_spirit_state_handles_missing_and_bad_widgets():
    # svars/text_widgets not dict -> defaults, bad .get() -> defaults
    assert collect_national_spirit_state(None, None, None)["mod_id"] == ""
    assert (
        collect_national_spirit_state({}, {"allowed": _BadVar()}, [])["allowed"] == ""
    )

    # widget that only supports .get() without args (TypeError branch)
    class OnlyNoArg:
        def get(self):
            return "has_war = yes"

    state = collect_national_spirit_state({}, {"allowed": OnlyNoArg()}, [])
    assert state["allowed"] == "has_war = yes"
    # non-string scalar coerced
    assert (
        collect_national_spirit_state({"mod_id": _FakeVar(123)}, {}, [])["mod_id"]
        == "123"
    )
    # whitespace-only Text -> stripped to ""
    assert (
        collect_national_spirit_state({}, {"allowed": _FakeText("   \n")}, [])[
            "allowed"
        ]
        == ""
    )
    # widget without .get attribute
    assert collect_national_spirit_state({"mod_id": object()}, {}, [])["mod_id"] == ""


def test_collect_dyn_mod_state_handles_whitespace_and_bad_widgets():
    assert collect_dyn_mod_state(None, None)["scope"] == "country"
    assert collect_dyn_mod_state({}, {"enable": _BadVar()})["enable"] == ""
    # scope empty string propagates (generator will treat "" != "country")
    assert collect_dyn_mod_state({"scope": _FakeVar("")}, {})["scope"] == ""
    # whitespace Text stripped to ""
    assert collect_dyn_mod_state({}, {"enable": _FakeText("  \n")})["enable"] == ""


def test_collect_additional_income_state_handles_bad_and_missing():
    assert collect_additional_income_state(None)["mode"] == "wire_only"
    # bad .get -> default
    assert collect_additional_income_state({"idea_id": _BadVar()})["idea_id"] == ""
    # widget without .get -> default
    assert collect_additional_income_state({"idea_id": object()})["idea_id"] == ""
    # non-string tag upper-cased via str()
    assert (
        collect_additional_income_state({"country_tag": _FakeVar(123)})["country_tag"]
        == "123"
    )


def test_collect_event_state_accepts_any_iterable_and_is_shallow():
    snap_tuple = collect_event_state((1, 2, 3))
    assert snap_tuple == [1, 2, 3]
    # shallow copy: objects are shared
    obj = SimpleNamespace(eid="a.1")
    snap = collect_event_state([obj])
    obj.eid = "mutated"
    assert snap[0].eid == "mutated"


def test_national_spirit_and_dyn_mod_integration_roundtrip():
    # Contract: collected state must be a valid generator input without extra glue.
    ns_state = collect_national_spirit_state(
        {"mod_id": _FakeVar("TAG_s"), "slot": _FakeVar("country")},
        {"allowed": _FakeText("always = yes"), "extra": _FakeText("")},
        [{"key": "stability_factor", "value": "0.05"}],
    )
    ns_out = build_national_spirit_output(**ns_state)
    assert "TAG_s = {" in ns_out
    assert "stability_factor = 0.05" in ns_out
    dm_state = collect_dyn_mod_state(
        {"mod_id": _FakeVar("TAG_dyn")},
        {"mods": _FakeText("stability_factor = my_var")},
    )
    dm_out = build_dyn_mod_output(**dm_state)
    assert "TAG_dyn = {" in dm_out
    assert "stability_factor = my_var" in dm_out
