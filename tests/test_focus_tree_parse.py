"""Tests for hoi4cm.focus_tree.parse — text -> structured data, no field loss."""

import threading

import pytest

import hoi4cm.focus_tree.parse as parse_module
from hoi4cm.focus_tree.parse import (
    EmptyFocusTreeError,
    FocusTreeParseBudgetExceeded,
    FocusTreeParseCancelled,
    parse_focus_tree,
)

# Tab-indented like real HOI4 files (\t -> tab in this non-raw string).
WRAPPED = """\
focus_tree = {
\tid = TST_shared_tree
\tcountry = {
\t\tfactor = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tcontinuous_focus_position = { x = 50 y = 1200 }
\tshared_focus = OTHER_shared

\tfocus = {
\t\tid = TST_alpha
\t\ticon = GFX_goal_generic_demand_territory
\t\tx = 4
\t\ty = 0
\t\tcost = 7
\t\tsearch_filters = { FOCUS_FILTER_POLITICAL }
\t\tavailable = {
\t\t\thas_war = no
\t\t}
\t\tcompletion_reward = {
\t\t\tadd_political_power = 120
\t\t}
\t\tai_will_do = { factor = 3 }
\t}

\tfocus = {
\t\tid = TST_beta
\t\ticon = GFX_goal_generic_political_pressure
\t\tx = 1
\t\ty = 1
\t\trelative_position_id = TST_alpha
\t\toffset = {
\t\t\tx = 2
\t\t\ty = 0
\t\t\ttrigger = {
\t\t\t\toriginal_tag = TST
\t\t\t}
\t\t}
\t\tprerequisite = { focus = TST_alpha }
\t\tmutually_exclusive = { focus = TST_alpha }
\t\tcompletion_reward = {
\t\t\tadd_stability = 0.05
\t\t}
\t}
}
"""

NO_WRAPPER = """\
joint_focus = {
\tid = JNT_one
\ticon = GFX_goal_generic_political_pressure
\tx = 0
\ty = 0
\tcost = 10
\tjoint_trigger = {
\t\tis_ai = no
\t}
\tcompletion_reward = {
\t\tadd_political_power = 50
\t}
}
"""

COUNTRY_BUDGET_TREE = """\
focus_tree = {
\tid = bounded_country
\tcountry = {
\t\tfactor = 0
\t}
\tfocus = {
\t\tid = TST_country_focus
\t\tx = 0
\t\ty = 0
\t}
}
"""

# focus_tree = { } wrappers holding only shared_focus/joint_focus blocks (or a
# mix), used to pin issue #123: had_wrapper must reflect that a wrapper was
# parsed, not just that a plain `focus` key was found.
WRAPPED_JOINT_ONLY = """\
focus_tree = {
\tid = TST_joint_tree
\tcountry = {
\t\tfactor = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tcontinuous_focus_position = { x = 0 y = 0 }
\tjoint_focus = {
\t\tid = TST_joint_one
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 50
\t\t}
\t}
}
"""

WRAPPED_SHARED_ONLY = """\
focus_tree = {
\tid = TST_shared_only_tree
\tcountry = {
\t\tfactor = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tcontinuous_focus_position = { x = 0 y = 0 }
\tshared_focus = {
\t\tid = TST_shared_one
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 50
\t\t}
\t}
}
"""

WRAPPED_MIXED = """\
focus_tree = {
\tid = TST_mixed_tree
\tcountry = {
\t\tfactor = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tcontinuous_focus_position = { x = 0 y = 0 }
\tfocus = {
\t\tid = TST_mixed_focus
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 50
\t\t}
\t}
\tshared_focus = {
\t\tid = TST_mixed_shared
\t\ticon = GFX_x
\t\tx = 1
\t\ty = 1
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 25
\t\t}
\t}
}
"""


def test_parse_tree_metadata():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    assert p.tree_id == "TST_shared_tree"
    assert p.cfp_x == 50
    assert p.cfp_y == 1200
    assert p.country_tag == "TST"
    assert p.shared_refs == ["OTHER_shared"]
    assert p.had_wrapper is True
    assert [f["id"] for f in p.focuses_data] == ["TST_alpha", "TST_beta"]


def test_parse_tree_extras_empty_when_no_unknown_wrapper_keys():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    assert p.tree_extras == {}


def test_parse_tree_extras_captures_unknown_wrapper_keys():
    """default/reset_on_civilwar/initial_show_position aren't named fields on
    ParsedFocusTree — they must survive via tree_extras (issue #39)."""
    src = """\
focus_tree = {
\tid = TST_extras_tree
\tcountry = {
\t\tfactor = 0
\t}
\tdefault = yes
\treset_on_civilwar = no
\tinitial_show_position = yes
\tcontinuous_focus_position = { x = 0 y = 0 }
\tshared_focus = OTHER_shared
\tfocus = {
\t\tid = TST_only
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t}
}
"""
    p = parse_focus_tree(src, "/tmp/x.txt")
    # Known wrapper fields (id, country, continuous_focus_position, focus,
    # shared_focus) must NOT leak into tree_extras — only genuinely unknown
    # keys belong there.
    assert p.tree_extras == {
        "default": "yes",
        "reset_on_civilwar": "no",
        "initial_show_position": "yes",
    }


def test_parse_keeps_focus_fields():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    alpha, beta = p.focuses_data
    assert alpha["icon"] == "GFX_goal_generic_demand_territory"
    assert alpha["x"] == "4"
    assert alpha["cost"] == "7"
    assert alpha["ai_will_do"] == {"factor": "3"}
    assert beta["relative_position_id"] == "TST_alpha"
    assert beta["prerequisite"] == {"focus": "TST_alpha"}
    assert beta["mutually_exclusive"] == {"focus": "TST_alpha"}


def test_parse_raw_rewards_and_conditions():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    assert "add_political_power = 120" in p.raw_rewards["TST_alpha"]
    assert "has_war = no" in p.raw_rewards[("TST_alpha", "available")]
    assert "add_stability = 0.05" in p.raw_rewards["TST_beta"]


def test_raw_key_scan_does_not_confuse_prefixed_and_suffixed_keys():
    """The single-pass raw-key scan must key each block to the right name.

    ``bypass`` is a prefix of ``bypass_effect`` and the alternation is
    deliberately unanchored, so this pins that ``bypass_effect = {`` is not
    also read as ``bypass``, and that a ``custom_``-prefixed key still counts
    (which is what the per-key ``re.search`` it replaced did).
    """
    source = """focus_tree = {
\tid = keys_tree
\tfocus = {
\t\tid = keys_focus
\t\tbypass_effect = { set_country_flag = from_bypass_effect }
\t\tcustom_available = { has_war = from_custom_available }
\t\tcancel = { has_war = from_cancel }
\t}
}"""

    rewards = parse_focus_tree(source, "/tmp/keys.txt").raw_rewards

    assert "from_bypass_effect" in rewards[("keys_focus", "bypass_effect")]
    assert ("keys_focus", "bypass") not in rewards
    assert "from_custom_available" in rewards[("keys_focus", "available")]
    assert "from_cancel" in rewards[("keys_focus", "cancel")]


def test_raw_key_scan_keeps_the_first_occurrence_of_a_repeated_key():
    source = """focus_tree = {
\tid = dup_tree
\tfocus = {
\t\tid = dup_focus
\t\tavailable = { has_war = first }
\t\tavailable = { has_war = second }
\t}
}"""

    rewards = parse_focus_tree(source, "/tmp/dup.txt").raw_rewards

    assert "first" in rewards[("dup_focus", "available")]
    assert "second" not in rewards[("dup_focus", "available")]


def test_parse_structured_offsets():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    offsets = p.raw_rewards[("TST_beta", "_offsets")]
    assert len(offsets) == 1
    assert offsets[0]["x"] == 2
    assert offsets[0]["y"] == 0
    assert "original_tag = TST" in offsets[0]["trigger"]


def test_parse_no_wrapper_fallback():
    p = parse_focus_tree(NO_WRAPPER, "/tmp/joint_file.txt")
    assert p.had_wrapper is False
    # No focus_tree wrapper -> tree name falls back to the filename.
    assert p.tree_id == "joint_file"
    assert [f["id"] for f in p.focuses_data] == ["JNT_one"]
    assert "joint_trigger" in p.raw_rewards[("JNT_one", "_joint_extra")]
    assert "is_ai = no" in p.raw_rewards[("JNT_one", "_joint_extra")]


def test_malformed_nested_focus_fallback_recovers_each_focus():
    source = """\
focus_tree = {
	id = broken_tree
	focus = {
		id = broken_first
	}
	focus = {
		id = broken_second
		focus = {
			id = broken_nested
		}
}
"""

    parsed = parse_focus_tree(source, "/tmp/broken.txt")

    assert [focus["id"] for focus in parsed.focuses_data] == [
        "broken_first",
        "broken_second",
        "broken_nested",
    ]


def test_nested_focus_rescans_are_bounded(monkeypatch):
    depth = 8000
    source = "focus = {\n" * depth + "id = too_deep\n" + "}\n" * depth
    real_match_brace = parse_module.match_brace
    scan_costs = []

    def count_scan(source_text, start):
        end = real_match_brace(source_text, start)
        scan_costs.append(end - start)
        return end

    monkeypatch.setattr(parse_module, "match_brace", count_scan)

    with pytest.raises(FocusTreeParseBudgetExceeded, match="parse budget exhausted"):
        parse_focus_tree(source, "/tmp/too_deep.txt")

    assert scan_costs == []


@pytest.mark.parametrize(
    ("limit", "attempts", "expected_calls", "expected_results"),
    [
        (3, 2, 2, [True, True]),  # below the scan limit
        (2, 2, 2, [True, True]),  # exactly the scan limit
        (2, 3, 2, [True, True, False]),  # one attempt beyond the limit
    ],
)
def test_raw_rescan_budget_scan_limit_boundaries(
    monkeypatch, limit, attempts, expected_calls, expected_results
):
    calls = 0

    def match(source, start):
        nonlocal calls
        calls += 1
        return start + 1

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", limit)
    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCAN_CHARS", 100)
    monkeypatch.setattr(parse_module, "match_brace", match)
    budget = parse_module._RawRescanBudget()

    results = [budget.match("x", 0) is not None for _ in range(attempts)]

    assert calls == expected_calls
    assert results == expected_results
    assert budget.exhausted is (not all(expected_results))


@pytest.mark.parametrize(
    ("limit", "cost", "attempts", "expected_calls", "expected_results"),
    [
        (5, 3, 1, 1, [True]),  # below the character limit
        (4, 2, 2, 2, [True, True]),  # exactly the character limit
        (5, 3, 2, 2, [True, False]),  # cumulative cost exceeds the limit
    ],
)
def test_raw_rescan_budget_char_limit_boundaries(
    monkeypatch, limit, cost, attempts, expected_calls, expected_results
):
    calls = 0

    def match(source, start):
        nonlocal calls
        calls += 1
        return start + cost

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 100)
    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCAN_CHARS", limit)
    monkeypatch.setattr(parse_module, "match_brace", match)
    budget = parse_module._RawRescanBudget()

    results = [budget.match("x", 0) is not None for _ in range(attempts)]

    assert calls == expected_calls
    assert results == expected_results
    assert budget.exhausted is (not all(expected_results))


def test_raw_rescan_budget_rejects_oversized_single_scan(monkeypatch):
    calls = 0

    def match(source, start):
        nonlocal calls
        calls += 1
        return start + 6

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 100)
    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCAN_CHARS", 5)
    monkeypatch.setattr(parse_module, "match_brace", match)
    budget = parse_module._RawRescanBudget()

    assert budget.match("x", 0) is None
    assert budget.scans == 1
    assert budget.chars == 6
    assert budget.exhausted
    assert calls == 1


def test_raw_rescan_budget_bounds_oversized_scan_input(monkeypatch):
    source = "prefix{" + "x" * 100
    start = source.index("{")
    seen = []

    def match(source_text, open_index, end_index=None):
        seen.append((source_text, open_index, end_index))
        return end_index if end_index is not None else len(source_text)

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 100)
    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCAN_CHARS", 5)
    monkeypatch.setattr(parse_module, "match_brace", match)
    budget = parse_module._RawRescanBudget()

    assert budget.match(source, start) is None
    assert len(seen) == 1
    received_source, open_index, end_index = seen[0]
    assert received_source is source
    assert open_index == start
    assert end_index == start + 6
    assert end_index - open_index == 6


def test_raw_rescan_budget_preserves_absolute_end_index(monkeypatch):
    source = "prefix{}"
    start = source.index("{")
    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 1)
    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCAN_CHARS", 1)

    budget = parse_module._RawRescanBudget()

    assert budget.match(source, start) == source.index("}")


def _country_budget_costs():
    txt = parse_module.strip_comments(COUNTRY_BUDGET_TREE)
    focus_start = parse_module.focus_block_starts(txt)[0]
    country_start = txt.index("{", txt.index("country ="))
    real_match_brace = parse_module.match_brace
    return (
        real_match_brace(txt, focus_start) - focus_start,
        real_match_brace(txt, country_start) - country_start,
    )


def test_parse_country_raw_consumes_shared_scan_budget(monkeypatch):
    scans = []
    real_match_brace = parse_module.match_brace

    def count_scan(source, start, end_index=None):
        end = real_match_brace(source, start, end_index)
        scans.append((start, end - start))
        return end

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 1)
    monkeypatch.setattr(parse_module, "match_brace", count_scan)

    with pytest.raises(FocusTreeParseBudgetExceeded, match="parse budget exhausted"):
        parse_focus_tree(COUNTRY_BUDGET_TREE, "/tmp/country-budget.txt")

    assert len(scans) == 1


def test_parse_country_raw_exact_shared_scan_budget_succeeds(monkeypatch):
    scans = []
    real_match_brace = parse_module.match_brace

    def count_scan(source, start, end_index=None):
        end = real_match_brace(source, start, end_index)
        scans.append((start, end - start))
        return end

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 2)
    monkeypatch.setattr(parse_module, "match_brace", count_scan)

    parsed = parse_focus_tree(COUNTRY_BUDGET_TREE, "/tmp/country-budget.txt")

    assert parsed.country_raw.strip() == "factor = 0"
    assert len(scans) == 2


def test_parse_country_raw_exact_shared_char_budget_succeeds(monkeypatch):
    focus_cost, country_cost = _country_budget_costs()
    scans = []
    real_match_brace = parse_module.match_brace

    def count_scan(source, start, end_index=None):
        end = real_match_brace(source, start, end_index)
        scans.append((start, end - start))
        return end

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 100)
    monkeypatch.setattr(
        parse_module, "MAX_RAW_BLOCK_RESCAN_CHARS", focus_cost + country_cost
    )
    monkeypatch.setattr(parse_module, "match_brace", count_scan)

    parsed = parse_focus_tree(COUNTRY_BUDGET_TREE, "/tmp/country-budget.txt")

    assert parsed.country_raw.strip() == "factor = 0"
    assert sum(cost for _start, cost in scans) == focus_cost + country_cost


def test_parse_country_raw_char_budget_overflow_is_rejected(monkeypatch):
    focus_cost, country_cost = _country_budget_costs()
    scans = []
    real_match_brace = parse_module.match_brace

    def count_scan(source, start, end_index=None):
        end = real_match_brace(source, start, end_index)
        scans.append((start, end - start))
        return end

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 100)
    monkeypatch.setattr(
        parse_module,
        "MAX_RAW_BLOCK_RESCAN_CHARS",
        focus_cost + country_cost - 1,
    )
    monkeypatch.setattr(parse_module, "match_brace", count_scan)

    with pytest.raises(FocusTreeParseBudgetExceeded, match="parse budget exhausted"):
        parse_focus_tree(COUNTRY_BUDGET_TREE, "/tmp/country-budget.txt")

    assert len(scans) == 2


def test_parse_rejects_when_rescan_scan_budget_is_exhausted(monkeypatch):
    source = """\
focus_tree = {
	id = broken_tree
	focus = {
		id = broken_first
	}
	focus = {
		id = broken_second
		focus = {
			id = broken_nested
		}
}
"""
    real_match_brace = parse_module.match_brace
    scans = 0

    def count_scan(source_text, start):
        nonlocal scans
        scans += 1
        return real_match_brace(source_text, start)

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 3)
    monkeypatch.setattr(parse_module, "match_brace", count_scan)

    with pytest.raises(FocusTreeParseBudgetExceeded, match="parse budget exhausted"):
        parse_focus_tree(source, "/tmp/budget.txt")

    assert scans == 3


def test_parse_rejects_when_raw_reward_budget_is_exhausted(
    monkeypatch,
):
    source = """\
focus_tree = {
\tid = bounded_tree
\tfocus = {
\t\tid = bounded_focus
\t\tcompletion_reward = {
\t\t\tadd_political_power = 1
\t\t}
\t\toffset = {
\t\t\tx = 1
\t\t\ty = 2
\t\t\ttrigger = {
\t\t\t\thas_war = no
\t\t\t}
\t\t}
\t}
}
"""
    real_match_brace = parse_module.match_brace
    scans = 0

    def count_scan(source_text, start):
        nonlocal scans
        scans += 1
        return real_match_brace(source_text, start)

    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 1)
    monkeypatch.setattr(parse_module, "match_brace", count_scan)

    with pytest.raises(FocusTreeParseBudgetExceeded, match="parse budget exhausted"):
        parse_focus_tree(source, "/tmp/budget-nested.txt")

    assert scans == 1


def test_parse_cancellation_callback_stops_raw_reward_scan():
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 4

    with pytest.raises(FocusTreeParseCancelled):
        parse_focus_tree(WRAPPED, "/tmp/cancelled.txt", cancelled=cancelled)


def test_parse_cancellation_event_stops_per_block_fallback(monkeypatch):
    source = """\
focus_tree = {
	id = broken_tree
	focus = {
		id = broken_first
	}
	focus = {
		id = broken_second
		focus = {
			id = broken_nested
		}
}
"""
    cancelled = threading.Event()
    real_match_brace = parse_module.match_brace
    scans = 0

    def cancel_on_fallback(source_text, start):
        nonlocal scans
        scans += 1
        end = real_match_brace(source_text, start)
        if scans == 4:
            cancelled.set()
        return end

    monkeypatch.setattr(parse_module, "match_brace", cancel_on_fallback)

    with pytest.raises(FocusTreeParseCancelled):
        parse_focus_tree(source, "/tmp/cancelled-fallback.txt", cancelled=cancelled)

    assert scans == 4


@pytest.mark.parametrize(
    "src,ids",
    [
        (WRAPPED_JOINT_ONLY, ["TST_joint_one"]),
        (WRAPPED_SHARED_ONLY, ["TST_shared_one"]),
        (WRAPPED_MIXED, ["TST_mixed_focus", "TST_mixed_shared"]),
    ],
)
def test_had_wrapper_true_for_shared_or_joint_only_wrapper(src, ids):
    """Issue #123: a wrapper holding only shared_focus/joint_focus blocks (or
    a mix) must still be recorded as wrapped, not just one with a plain
    `focus` key."""
    p = parse_focus_tree(src, "/tmp/x.txt")
    assert p.had_wrapper is True
    assert [f["id"] for f in p.focuses_data] == ids


def test_parse_strips_bom():
    p = parse_focus_tree("﻿" + NO_WRAPPER, "/tmp/joint_file.txt")
    assert [f["id"] for f in p.focuses_data] == ["JNT_one"]


def test_parse_empty_raises_with_block_diagnostic():
    # Has a focus_tree keyword but no valid focus IDs inside.
    src = "focus_tree = {\n\tid = X\n}\n"
    with pytest.raises(EmptyFocusTreeError) as exc:
        parse_focus_tree(src, "/tmp/bad.txt")
    msg = str(exc.value)
    assert "No focus data found in bad.txt" in msg
    assert "Blocks found: focus_tree" in msg


def test_parse_empty_no_blocks_diagnostic():
    with pytest.raises(EmptyFocusTreeError) as exc:
        parse_focus_tree("# only a comment\nfoo = bar\n", "/tmp/none.txt")
    assert "No recognized block types found." in str(exc.value)


def test_empty_focus_tree_error_is_value_error():
    assert issubclass(EmptyFocusTreeError, ValueError)


def test_parse_quoted_hash_and_braces_without_losing_following_fields():
    source = """focus_tree = {
    id = quoted_tree
    focus = {
        id = quoted_focus
        custom_text = "value # with { braces } inside"
        x = 3 # real comment }
        y = 4
    }
}"""

    parsed = parse_focus_tree(source, "/tmp/quoted.txt")

    assert parsed.focuses_data[0]["custom_text"] == "value # with { braces } inside"
    assert parsed.focuses_data[0]["x"] == "3"
    assert parsed.focuses_data[0]["y"] == "4"
