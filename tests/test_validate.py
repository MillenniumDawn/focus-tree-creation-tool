from hoi4cm.focus_tree.validate import (
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


def test_empty_effects_is_warning_not_error():
    a = _focus(1, name="A", effects=[])
    doc = FocusDocument([a])
    issues = validate_document(doc)
    empty = [it for it in issues if it.code == "empty_effects"]
    assert empty
    assert empty[0].severity == "warning"


def test_default_icon_is_warning():
    a = _focus(1, name="A", gfx="GFX_goal_generic_political_pressure")
    doc = FocusDocument([a])
    issues = validate_document(doc)
    assert any(it.code == "default_icon" and it.severity == "warning" for it in issues)


def test_gfx_missing_detected_when_sprites_supplied():
    a = _focus(1, name="A", gfx="GFX_custom_missing")
    doc = FocusDocument([a])
    issues = validate_document(doc, sprites={"GFX_other": "/path"})
    assert any(it.code == "gfx_missing" for it in issues)
    # not flagged when sprites is None
    issues2 = validate_document(doc, sprites=None)
    assert not any(it.code == "gfx_missing" for it in issues2)


def test_position_collision_detected():
    a = _focus(1, name="A", x=0, y=0)
    b = _focus(2, name="B", x=0, y=0)
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    assert any(it.code == "position_collision" for it in issues)


def test_unresolvable_relative_position():
    a = _focus(1, name="A")
    b = _focus(2, name="B", rel="NONEXISTENT")
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    assert any(it.code == "relative_position_unresolved" for it in issues)
    # resolvable should not flag
    c = _focus(3, name="C", rel="A")
    doc2 = FocusDocument([a, c])
    assert not any(
        it.code == "relative_position_unresolved" for it in validate_document(doc2)
    )


def test_duplicate_name_detected():
    a = _focus(1, name="dup")
    b = _focus(2, name="dup")
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    assert any(it.code == "duplicate_name" for it in issues)


def test_prereq_cycle_detected():
    a = _focus(1, name="A", prereqs=[[2]])
    b = _focus(2, name="B", prereqs=[[1]])
    doc = FocusDocument([a, b])
    issues = validate_document(doc)
    assert any(it.code == "prereq_cycle" for it in issues)
    # acyclic should not flag
    c = _focus(3, name="C", prereqs=[[1]])
    doc2 = FocusDocument([a, c])  # A has no prereq now
    a2 = _focus(1, name="A")
    doc2 = FocusDocument([a2, c])
    assert not any(it.code == "prereq_cycle" for it in validate_document(doc2))


def test_loc_missing_when_keys_supplied():
    a = _focus(1, name="my_focus")
    doc = FocusDocument([a])
    issues = validate_document(doc, loc_keys=set())
    assert any(it.code == "loc_missing" for it in issues)
    assert any(it.code == "loc_missing_desc" for it in issues)
    # with keys present, no warning
    issues2 = validate_document(doc, loc_keys={"my_focus", "my_focus_desc"})
    assert not any(it.code.startswith("loc_missing") for it in issues2)


def test_collect_loc_keys_from_text():
    text = 'l_english:\n my_focus: "Title"\n my_focus_desc: "Desc"\n'
    keys = collect_loc_keys_from_text(text)
    assert keys == {"my_focus", "my_focus_desc"}
    assert collect_loc_keys_from_text(None) is None


def test_worst_severity_per_focus():
    a = _focus(1, name="A")
    b = _focus(2, name="B")
    doc = FocusDocument([a, b])
    # A will have error (broken prereq), B warning (empty)
    b.effects = []
    a.prereqs = [[99]]
    issues = validate_document(doc)
    worst = worst_severity_per_focus(issues)
    assert worst[a.id] == "error"
    # B should be warning (empty_effects outweighs maybe)
    assert worst.get(b.id) in ("warning", "error")


def test_validate_is_pure_and_sorted():
    a = _focus(2, name="Z", x=0, y=0)
    b = _focus(1, name="A", x=0, y=0)
    doc = FocusDocument([a, b])
    issues1 = validate_document(doc)
    issues2 = validate_document(doc)
    assert issues1 == issues2
    # sorted by severity then name
    severities = [it.severity for it in issues1]
    # errors come before warnings
    if "error" in severities and "warning" in severities:
        assert severities.index("error") < severities.index("warning")
