from hoi4cm.focus_tree.validate import (
    DEFAULT_GFX,
    Issue,
    collect_loc_keys_from_text,
    validate_document,
    worst_severity_per_focus,
)
from hoi4cm.models import Focus, FocusDocument


def _focus(  # type: ignore[no-untyped-def]
    fid,
    name=None,
    x=0,
    y=0,
    gfx="GFX_test",
    effects=None,
    prereqs=None,
    mutex=None,
    rel=None,
):
    f = Focus(x, y)
    f.id = fid
    f.name = name or f"focus_{fid}"
    f.gfx = gfx
    f.effects = effects if effects is not None else [{"type": "dummy", "fields": {}}]
    f.prereqs = prereqs if prereqs is not None else []
    f.mutex = mutex if mutex is not None else []
    f.relative_position_id = rel
    return f


def test_empty_mapping_returns_no_issues():
    assert validate_document({}) == []


def test_empty_focus_document_returns_no_issues():
    assert validate_document(FocusDocument([])) == []


def test_valid_tree_with_custom_gfx_and_effects_is_clean():
    a = _focus(1, name="A", gfx="GFX_custom", effects=[{"type": "x", "fields": {}}])
    b = _focus(2, name="B", x=1, y=0, gfx="GFX_custom2")
    # B depends on A
    b.prereqs = [[1]]
    doc = FocusDocument([a, b])
    issues = validate_document(doc, sprites={"GFX_custom": "/a", "GFX_custom2": "/b"})
    # fully clean when gfx known, effects present, no collision
    assert issues == []


def test_broken_prereq_and_mutex_reported_as_error():
    a = _focus(1, name="A")
    b = _focus(2, name="B", prereqs=[[99]], mutex=[100])
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    codes = {it.code for it in issues}
    assert "broken_prereq" in codes
    assert "broken_mutex" in codes
    assert all(
        it.severity == "error"
        for it in issues
        if it.code in ("broken_prereq", "broken_mutex")
    )
    # message contains focus name and id
    prereq = next(it for it in issues if it.code == "broken_prereq")
    assert prereq.focus_id == 2
    assert prereq.field == "prereqs"
    assert "B" in prereq.message


def test_broken_prereq_mixed_valid_and_invalid_groups():
    a = _focus(1, name="A")
    b = _focus(2, name="B", prereqs=[[1, 99], [1]])
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    bad = [it for it in issues if it.code == "broken_prereq"]
    assert len(bad) == 1
    assert "99" in bad[0].message
    assert bad[0].field == "prereqs"


def test_valid_prereq_and_mutex_not_flagged():
    a = _focus(1, name="A")
    b = _focus(2, name="B", prereqs=[[1]], mutex=[1])
    a.mutex = [2]
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    assert not any(it.code in ("broken_prereq", "broken_mutex") for it in issues)


def test_empty_effects_is_warning_not_error():
    a = _focus(1, name="A", effects=[])
    doc = FocusDocument([a])
    issues = validate_document(doc)
    empty = [it for it in issues if it.code == "empty_effects"]
    assert empty
    assert empty[0].severity == "warning"
    assert empty[0].field == "effects"


def test_default_icon_is_warning():
    a = _focus(1, name="A", gfx=DEFAULT_GFX)
    doc = FocusDocument([a])
    issues = validate_document(doc)
    assert any(it.code == "default_icon" and it.severity == "warning" for it in issues)


def test_missing_gfx_field_treated_as_default():
    a = _focus(1, name="A", gfx="")
    doc = FocusDocument([a])
    issues = validate_document(doc)
    assert any(it.code == "default_icon" for it in issues)


def test_default_icon_suppressible():
    a = _focus(1, name="A", gfx=DEFAULT_GFX)
    doc = FocusDocument([a])
    issues = validate_document(doc, include_default_icon_warning=False)
    assert not any(it.code == "default_icon" for it in issues)


def test_gfx_missing_detected_when_sprites_supplied():
    a = _focus(1, name="A", gfx="GFX_custom_missing")
    doc = FocusDocument([a])
    issues = validate_document(doc, sprites={"GFX_other": "/path"})
    assert any(it.code == "gfx_missing" for it in issues)
    flagged = next(it for it in issues if it.code == "gfx_missing")
    assert flagged.severity == "warning"
    assert flagged.field == "gfx"
    # not flagged when sprites is None
    issues2 = validate_document(doc, sprites=None)
    assert not any(it.code == "gfx_missing" for it in issues2)


def test_gfx_missing_not_double_reported_for_default():
    a = _focus(1, name="A", gfx=DEFAULT_GFX)
    doc = FocusDocument([a])
    issues = validate_document(doc, sprites={"GFX_other": "/x"})
    assert any(it.code == "default_icon" for it in issues)
    assert not any(it.code == "gfx_missing" for it in issues)
    # when default warning suppressed, default gfx should surface as gfx_missing
    issues2 = validate_document(
        doc, sprites={"GFX_other": "/x"}, include_default_icon_warning=False
    )
    assert any(it.code == "gfx_missing" for it in issues2)


def test_known_gfx_not_flagged():
    a = _focus(1, name="A", gfx="GFX_known")
    doc = FocusDocument([a])
    issues = validate_document(doc, sprites={"GFX_known": "/p"})
    assert not any(it.code == "gfx_missing" for it in issues)


def test_position_collision_detected():
    a = _focus(1, name="A", x=0, y=0)
    b = _focus(2, name="B", x=0, y=0)
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    coll = [it for it in issues if it.code == "position_collision"]
    assert len(coll) == 1
    assert coll[0].severity == "error"
    assert "A" in coll[0].message and "B" in coll[0].message
    assert coll[0].field == "x"


def test_position_collision_with_three_occupants_single_issue():
    a = _focus(1, name="A", x=5, y=5)
    b = _focus(2, name="B", x=5, y=5)
    c = _focus(3, name="C", x=5, y=5)
    doc = FocusDocument([a, b, c])
    coll = [it for it in validate_document(doc) if it.code == "position_collision"]
    assert len(coll) == 1
    assert "5" in coll[0].message


def test_plain_dict_fallback_for_occupied_positions():
    # Exercises the `occupied is None` branch (line 96-99)
    a = _focus(1, name="A", x=0, y=0)
    b = _focus(2, name="B", x=0, y=0)
    plain = {1: a, 2: b}
    issues = validate_document(plain)
    assert any(it.code == "position_collision" for it in issues)


def test_unresolvable_relative_position():
    a = _focus(1, name="A")
    b = _focus(2, name="B", rel="NONEXISTENT")
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    bad = [it for it in issues if it.code == "relative_position_unresolved"]
    assert len(bad) == 1
    assert bad[0].severity == "error"
    assert bad[0].field == "relative_position_id"
    assert "NONEXISTENT" in bad[0].message


def test_resolvable_relative_position_not_flagged():
    a = _focus(1, name="A")
    c = _focus(3, name="C", rel="A")
    doc = FocusDocument([a, c])
    assert not any(
        it.code == "relative_position_unresolved" for it in validate_document(doc)
    )


def test_empty_relative_position_id_not_flagged():
    a = _focus(1, name="A", rel="")
    doc = FocusDocument([a])
    assert not any(
        it.code == "relative_position_unresolved" for it in validate_document(doc)
    )
    b = _focus(2, name="B", rel=None)
    doc2 = FocusDocument([b])
    assert not any(
        it.code == "relative_position_unresolved" for it in validate_document(doc2)
    )


def test_duplicate_name_detected():
    a = _focus(1, name="dup")
    b = _focus(2, name="dup")
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    dup = [it for it in issues if it.code == "duplicate_name"]
    assert len(dup) == 1
    assert dup[0].severity == "error"
    assert dup[0].focus_id == 1
    assert "dup" in dup[0].message


def test_duplicate_name_with_three_ids_reports_once():
    a = _focus(1, name="dup")
    b = _focus(2, name="dup")
    c = _focus(3, name="dup")
    doc = FocusDocument([a, b, c])
    dup = [it for it in validate_document(doc) if it.code == "duplicate_name"]
    assert len(dup) == 1
    assert "3" in dup[0].message


def test_prereq_cycle_detected_two_nodes():
    a = _focus(1, name="A", prereqs=[[2]])
    b = _focus(2, name="B", prereqs=[[1]])
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    assert any(it.code == "prereq_cycle" for it in issues)
    cyc = next(it for it in issues if it.code == "prereq_cycle")
    assert cyc.severity == "error"
    assert "A" in cyc.message or "B" in cyc.message


def test_prereq_self_cycle_detected():
    a = _focus(1, name="A", prereqs=[[1]])
    doc = FocusDocument([a])
    assert any(it.code == "prereq_cycle" for it in validate_document(doc))


def test_prereq_cycle_three_nodes():
    a = _focus(1, name="A", prereqs=[[2]])
    b = _focus(2, name="B", prereqs=[[3]])
    c = _focus(3, name="C", prereqs=[[1]])
    doc = FocusDocument([a, b, c])
    assert any(it.code == "prereq_cycle" for it in validate_document(doc))


def test_prereq_acyclic_chain_not_flagged():
    a = _focus(1, name="A")
    b = _focus(2, name="B", prereqs=[[1]])
    c = _focus(3, name="C", prereqs=[[2]])
    doc = FocusDocument([a, b, c])
    assert not any(it.code == "prereq_cycle" for it in validate_document(doc))


def test_prereq_cycle_deduped():
    # Diamond with single cycle should report once, not twice
    a = _focus(1, name="A", prereqs=[[2]])
    b = _focus(2, name="B", prereqs=[[1]])
    c = _focus(3, name="C", prereqs=[[1]])
    doc = FocusDocument([a, b, c])
    cycles = [it for it in validate_document(doc) if it.code == "prereq_cycle"]
    # sorted dedup key collapses; should be exactly one report for the A<->B cycle
    assert len(cycles) == 1


def test_loc_missing_when_keys_supplied():
    a = _focus(1, name="my_focus")
    doc = FocusDocument([a])
    issues = validate_document(doc, loc_keys=set())
    assert any(it.code == "loc_missing" for it in issues)
    assert any(it.code == "loc_missing_desc" for it in issues)
    # with keys present, no warning
    issues2 = validate_document(doc, loc_keys={"my_focus", "my_focus_desc"})
    assert not any(it.code.startswith("loc_missing") for it in issues2)


def test_loc_partial_keys_only_one_missing():
    a = _focus(1, name="my_focus")
    doc = FocusDocument([a])
    issues = validate_document(doc, loc_keys={"my_focus"})
    codes = {it.code for it in issues}
    assert "loc_missing_desc" in codes
    assert "loc_missing" not in codes


def test_loc_skipped_when_keys_none():
    a = _focus(1, name="my_focus")
    doc = FocusDocument([a])
    assert not any(
        it.code.startswith("loc_missing")
        for it in validate_document(doc, loc_keys=None)
    )


def test_collect_loc_keys_from_text():
    text = 'l_english:\n my_focus: "Title"\n my_focus_desc: "Desc"\n'
    keys = collect_loc_keys_from_text(text)
    assert keys == {"my_focus", "my_focus_desc"}
    assert collect_loc_keys_from_text(None) is None
    assert collect_loc_keys_from_text("") == set()


def test_collect_loc_keys_handles_version_suffix():
    text = ' my_key:1 "value"\n other:2: "v2"\n'
    keys = collect_loc_keys_from_text(text)
    assert keys is not None and "my_key" in keys
    # version suffix stripped by _KEY_RE
    assert keys is not None and "other" in keys


def test_worst_severity_per_focus_picks_error_over_warning():
    # a has only error, b has only warning
    a = _focus(1, name="A", x=0, y=0, prereqs=[[99]])
    b = _focus(2, name="B", x=10, y=10, effects=[])
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    worst = worst_severity_per_focus(issues)
    assert worst[a.id] == "error"
    assert worst[b.id] == "warning"


def test_worst_severity_ignores_none_focus_id_and_info():
    issues = [
        Issue("error", "broken_prereq", None, None, "global", field="prereqs"),
        Issue("info", "hint", 1, "A", "info msg"),
        Issue("warning", "empty_effects", 1, "A", "warn"),
        Issue("error", "position_collision", 1, "A", "err"),
    ]
    worst = worst_severity_per_focus(issues)
    assert worst[1] == "error"
    assert None not in worst


def test_validate_is_pure_returns_new_list_and_does_not_mutate():
    a = _focus(2, name="Z", x=0, y=0)
    b = _focus(1, name="A", x=0, y=0)
    doc = FocusDocument([a, b])
    issues1 = validate_document(doc)
    issues2 = validate_document(doc)
    assert issues1 is not issues2
    assert issues1 == issues2
    before = {fid: (f.x, f.y, list(f.prereqs)) for fid, f in doc.items()}
    validate_document(doc)
    after = {fid: (f.x, f.y, list(f.prereqs)) for fid, f in doc.items()}
    assert before == after


def test_validate_sorts_by_severity_error_before_warning():
    # one error (collision), one warning (empty)
    a = _focus(1, name="A", x=0, y=0)
    b = _focus(2, name="B", x=0, y=0, effects=[])
    # force known severities: collision error + empty warning; give distinct names
    # Use x=5 collision for A/B and empty on C
    c = _focus(3, name="C", x=5, y=5, effects=[])
    doc = FocusDocument([a, b, c])
    issues = validate_document(doc)
    severities = [it.severity for it in issues]
    assert "error" in severities and "warning" in severities
    assert severities.index("error") < severities.index("warning")


def test_validate_sorts_within_severity_by_name():
    a = _focus(1, name="Zebra", x=0, y=0)
    b = _focus(2, name="b2", x=0, y=0)
    c = _focus(3, name="Apple", x=1, y=1)
    d = _focus(4, name="d2", x=1, y=1)
    doc = FocusDocument([a, b, c, d])
    errors = [it for it in validate_document(doc) if it.code == "position_collision"]
    assert len(errors) == 2
    names = [it.focus_name or "" for it in errors]
    assert names == sorted(names)
    assert names == ["Apple", "Zebra"]


def test_validate_does_not_mutate_document():
    a = _focus(1, name="A", x=0, y=0)
    b = _focus(2, name="B", x=0, y=0)
    doc = FocusDocument([a, b])
    before = {fid: (f.x, f.y, list(f.prereqs)) for fid, f in doc.items()}
    validate_document(doc)
    after = {fid: (f.x, f.y, list(f.prereqs)) for fid, f in doc.items()}
    assert before == after


def test_issue_sort_key_orders_error_before_warning_before_info():
    err = Issue("error", "a", 1, "A", "m")
    warn = Issue("warning", "a", 1, "A", "m")
    info = Issue("info", "a", 1, "A", "m")
    assert err.sort_key() < warn.sort_key() < info.sort_key()


def test_multiple_issues_per_focus_all_reported():
    a = _focus(1, name="A", gfx="", effects=[], prereqs=[[99]], rel="MISSING")
    doc = FocusDocument([a])
    codes = {it.code for it in validate_document(doc)}
    assert "broken_prereq" in codes
    assert "relative_position_unresolved" in codes
    assert "empty_effects" in codes
    assert "default_icon" in codes
