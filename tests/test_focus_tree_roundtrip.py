"""Round-trip guard for the focus-tree pipeline.

parse -> build -> export -> reparse must be stable (no fields dropped). The
exporter normalizes whitespace, so the durable guarantee is *text idempotence*:
the second export equals the first. We also check that the structural fields
survive and that key content actually made it into the exported text.
"""

import os

import pytest
from test_focus_tree_parse import NO_WRAPPER, WRAPPED

from hoi4cm.core import read_file
from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.export import export_focus_tree
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import Focus

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "focus_trees")


@pytest.fixture(autouse=True)
def reset_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def raw_block_renderer(eff):
    """Mirror the monolith's _raw_block effect rendering (3-tab base indent)."""
    if eff.get("type") != "_raw_block":
        return ""
    raw = eff.get("fields", {}).get("raw", "").strip()
    return "\n".join(f"\t\t\t{ln}" for ln in raw.splitlines()) if raw else ""


def _info(parsed, tree_type):
    return {
        "type": tree_type,
        "file_path": "/tmp/x.txt",
        "tree_id": parsed.tree_id,
        "cfp_x": parsed.cfp_x,
        "cfp_y": parsed.cfp_y,
        "shared_focuses": parsed.shared_refs,
        "joint_focuses": parsed.joint_refs,
        "country_tag": parsed.country_tag,
        "had_wrapper": parsed.had_wrapper,
        "country_raw": parsed.country_raw,
        "tree_extras": parsed.tree_extras,
        "focus_ids": set(),
    }


def _load_and_export(src, tree_type, path="/tmp/x.txt"):
    parsed = parse_focus_tree(src, path)
    focuses = build_focuses(parsed, tree_idx=1)
    lookup = {f.id: f for f in focuses}
    text = export_focus_tree(
        focuses,
        _info(parsed, tree_type),
        focus_lookup=lookup,
        effect_renderer=raw_block_renderer,
    )
    return focuses, text


def _summary(focuses):
    by_id = {f.id: f.name for f in focuses}
    return [
        (
            f.name,
            f.gfx,
            f.cost,
            f.x,
            f.y,
            getattr(f, "relative_position_id", None),
            tuple(tuple(by_id.get(i, i) for i in grp) for grp in f.prereqs),
            tuple(by_id.get(i, i) for i in f.mutex),
            tuple((o["x"], o["y"]) for o in f.offsets),
            f.ai_will_do,
            f.search_filters,
        )
        for f in focuses
    ]


@pytest.mark.parametrize(
    "src,tree_type",
    [(WRAPPED, "shared"), (NO_WRAPPER, "joint")],
)
def test_export_is_idempotent(src, tree_type):
    _f1, t1 = _load_and_export(src, tree_type)
    _f2, t2 = _load_and_export(t1, tree_type)
    assert t1 == t2


@pytest.mark.parametrize(
    "src,tree_type",
    [(WRAPPED, "shared"), (NO_WRAPPER, "joint")],
)
def test_structural_fields_survive(src, tree_type):
    f1, t1 = _load_and_export(src, tree_type)
    f2, _t2 = _load_and_export(t1, tree_type)
    assert _summary(f1) == _summary(f2)


def test_wrapped_content_present():
    _f, t1 = _load_and_export(WRAPPED, "shared")
    for needle in (
        "focus_tree = {",
        "id = TST_shared_tree",
        "original_tag = TST",
        "continuous_focus_position = { x = 50 y = 1200 }",
        "shared_focus = OTHER_shared",
        "id = TST_alpha",
        "add_political_power = 120",
        "search_filters = { FOCUS_FILTER_POLITICAL }",
        "has_war = no",
        "relative_position_id = TST_alpha",
        "offset = {",
        "prerequisite = { focus = TST_alpha }",
        "mutually_exclusive = { focus = TST_alpha }",
        "factor = 3",
    ):
        assert needle in t1, needle


def test_joint_content_present():
    _f, t1 = _load_and_export(NO_WRAPPER, "joint")
    for needle in (
        "joint_focus = {",
        "id = JNT_one",
        "joint_trigger = {",
        "is_ai = no",
        "add_political_power = 50",
    ):
        assert needle in t1, needle


@pytest.mark.parametrize(
    "tree_type,had_wrapper,block_keyword",
    [
        ("shared", True, "focus"),
        ("shared", False, "shared_focus"),
        ("joint", False, "joint_focus"),
    ],
)
def test_extra_tree_export_preserves_main_tree_only_focus_fields(
    tree_type, had_wrapper, block_keyword
):
    focus = Focus(3, 4)
    focus.name = "TST_extra"
    focus.text = "TST_extra_custom_text"
    focus.allow_branch = "OR = {\n\thas_government = democratic\n}"
    focus.cancel_if_invalid = False
    focus.continue_if_invalid = True
    focus.available_if_capitulated = True
    info = {
        "tree_id": "TST_extra_tree",
        "country_tag": "TST",
        "cfp_x": 0,
        "cfp_y": 0,
        "type": tree_type,
        "had_wrapper": had_wrapper,
        "shared_focuses": [],
        "joint_focuses": [],
    }

    text = export_focus_tree(
        [focus],
        info,
        focus_lookup={focus.id: focus},
        effect_renderer=raw_block_renderer,
    )
    parsed = parse_focus_tree(text, "/tmp/x.txt")
    restored = build_focuses(parsed, tree_idx=1)[0]

    assert f"{block_keyword} = {{" in text
    assert "text = TST_extra_custom_text" in text
    focus_indent = "\t\t" if tree_type == "shared" and had_wrapper else "\t"
    assert (
        "allow_branch = {\n"
        f"{focus_indent}\tOR = {{\n"
        f"{focus_indent}\t\thas_government = democratic\n"
        f"{focus_indent}\t}}"
    ) in text
    assert "cancel_if_invalid = no" in text
    assert "continue_if_invalid = yes" in text
    assert "available_if_capitulated = yes" in text
    assert restored.text == focus.text
    assert "has_government = democratic" in restored.allow_branch
    assert restored.cancel_if_invalid is False
    assert restored.continue_if_invalid is True
    assert restored.available_if_capitulated is True


def _extra_tree_info(**overrides):
    info = {
        "tree_id": "TST_shared_tree",
        "country_tag": "TST",
        "cfp_x": 0,
        "cfp_y": 0,
        "type": "shared",
        "had_wrapper": True,
        "shared_focuses": [],
        "joint_focuses": [],
    }
    info.update(overrides)
    return info


def test_extra_tree_export_preserves_country_raw_verbatim():
    """export_focus_tree must not discard an imported country block (#39)."""
    focus = Focus(0, 0)
    focus.name = "TST_root"
    country_raw = "base = 0\nmodifier = {\n\tadd = 20\n\toriginal_tag=TST\n}"
    info = _extra_tree_info(country_raw=country_raw)

    text = export_focus_tree(
        [focus],
        info,
        focus_lookup={focus.id: focus},
        effect_renderer=raw_block_renderer,
    )
    expected_country_block = "\n".join(
        [
            "\tcountry = {",
            "\t\tbase = 0",
            "\t\tmodifier = {",
            "\t\t\tadd = 20",
            "\t\t\toriginal_tag=TST",
            "\t\t}",
            "\t}",
        ]
    )
    assert expected_country_block in text
    # The canned default must not also appear alongside the verbatim block.
    assert "factor = 0" not in text


def test_extra_tree_export_falls_back_to_canned_country_block_when_blank():
    focus = Focus(0, 0)
    focus.name = "TST_root"
    info = _extra_tree_info()  # no country_raw override -> blank

    text = export_focus_tree(
        [focus],
        info,
        focus_lookup={focus.id: focus},
        effect_renderer=raw_block_renderer,
    )
    assert "factor = 0" in text
    assert "original_tag = TST" in text


def test_extra_tree_export_emits_tree_extras():
    """Wrapper-level keys with no named field (default, reset_on_civilwar,
    initial_show_position, ...) must survive via tree_extras (#39)."""
    focus = Focus(0, 0)
    focus.name = "TST_root"
    info = _extra_tree_info(tree_extras={"default": "yes", "reset_on_civilwar": "no"})

    text = export_focus_tree(
        [focus],
        info,
        focus_lookup={focus.id: focus},
        effect_renderer=raw_block_renderer,
    )
    assert "\tdefault = yes" in text
    assert "\treset_on_civilwar = no" in text


def test_extra_tree_export_omits_tree_extras_block_when_empty():
    focus = Focus(0, 0)
    focus.name = "TST_root"
    info = _extra_tree_info()

    text = export_focus_tree(
        [focus],
        info,
        focus_lookup={focus.id: focus},
        effect_renderer=raw_block_renderer,
    )
    assert "default" not in text


def test_extra_tree_roundtrip_preserves_country_raw_and_tree_extras():
    """Full parse -> export -> reparse cycle for both fields at once."""
    src = """\
focus_tree = {
\tid = TST_shared_tree
\tcountry = {
\t\tbase = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tdefault = yes
\treset_on_civilwar = no
\tcontinuous_focus_position = { x = 0 y = 0 }
\tfocus = {
\t\tid = TST_only
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 1
\t\t}
\t}
}
"""
    focuses1, t1 = _load_and_export(src, "shared")
    focuses2, t2 = _load_and_export(t1, "shared")
    assert t1 == t2
    assert _summary(focuses1) == _summary(focuses2)
    assert "\tdefault = yes" in t1
    assert "\treset_on_civilwar = no" in t1
    assert "base = 0" in t1
    assert "factor = 0" not in t1  # canned block must not appear alongside it


# ── Fixture-file round-trips (see tests/fixtures/focus_trees/) ────────────

FIXTURE_FILES = [
    ("wrapper_basic.txt", "shared"),
    ("offset_original_tag.txt", "shared"),
    ("bare_focus.txt", "shared"),
    ("bare_shared_focus.txt", "shared"),
]


def _load_and_export_fixture(fname, tree_type):
    path = os.path.join(FIX_DIR, fname)
    raw = read_file(path)
    return _load_and_export(raw, tree_type, path=path)


@pytest.mark.parametrize("fname,tree_type", FIXTURE_FILES)
def test_fixture_export_is_idempotent(fname, tree_type):
    _f1, t1 = _load_and_export_fixture(fname, tree_type)
    _f2, t2 = _load_and_export(t1, tree_type)
    assert t1 == t2


@pytest.mark.parametrize("fname,tree_type", FIXTURE_FILES)
def test_fixture_structural_fields_survive(fname, tree_type):
    f1, t1 = _load_and_export_fixture(fname, tree_type)
    f2, _t2 = _load_and_export(t1, tree_type)
    assert _summary(f1) == _summary(f2)
