"""Tests for the Tk-free focus-tree export planning pipeline."""

import pytest

from hoi4cm.focus_tree.export_plan import (
    execute_export_plans,
    make_extra_export_plan,
    make_main_export_plan,
)
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_focus_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def _focus(name, tree_idx=0):
    focus = Focus(0, 0)
    focus.name = name
    focus.tree_idx = tree_idx
    return focus


def _main_plan(tmp_path, *, loc_language="english"):
    focus = _focus("TST_root")
    return make_main_export_plan(
        label="Main: TST_focus_tree",
        focus_path=str(tmp_path / "05_TST.txt"),
        loc_path=str(tmp_path / "MD_focus_TST_l_english.yml"),
        focuses=[focus],
        tree_info={
            "tree_id": "TST_focus_tree",
            "country_tag": "TST",
            "cfp_x": None,
            "cfp_y": None,
            "country_raw": "",
            "tree_extras": {},
            "shared_focuses": [],
            "joint_focuses": [],
        },
        focus_lookup={focus.id: focus},
        focus_name_lookup={focus.name: focus},
        loc_language=loc_language,
    )


def _extra_plan(tmp_path, name="TST_shared"):
    focus = _focus(name, tree_idx=1)
    return make_extra_export_plan(
        label="Shared: TST_shared_focuses",
        focus_path=str(tmp_path / f"{name}.txt"),
        focuses=[focus],
        tree_info={
            "type": "shared",
            "tree_id": "TST_shared_focuses",
            "country_tag": "TST",
            "country_raw": "",
            "cfp_x": None,
            "cfp_y": None,
            "had_wrapper": False,
        },
        focus_lookup={focus.id: focus},
        focus_name_lookup={focus.name: focus},
        extra_tree_idx=1,
    )


def test_main_plan_writes_tree_and_localisation_as_one_group(tmp_path):
    plan = _main_plan(tmp_path)
    calls = []

    results = execute_export_plans([plan], lambda entries: calls.append(tuple(entries)))

    assert len(results) == 1
    assert results[0].ok
    assert results[0].written_paths == (plan.focus_path, plan.loc_path)
    assert results[0].localisation_added == 2
    assert len(calls) == 1
    assert [path for path, _text, _encoding in calls[0]] == [
        plan.focus_path,
        plan.loc_path,
    ]
    assert "TST_root" in calls[0][0][1]
    assert "TST_root" in calls[0][1][1]


def test_main_plan_snapshots_non_english_localisation_header(tmp_path):
    plan = _main_plan(tmp_path, loc_language="french")
    calls = []

    execute_export_plans([plan], lambda entries: calls.append(tuple(entries)))

    assert calls[0][1][1].startswith("l_french:\n")


def test_main_plan_exports_german_localisation_header(tmp_path):
    plan = _main_plan(tmp_path, loc_language="german")
    calls = []

    execute_export_plans([plan], lambda entries: calls.append(tuple(entries)))

    assert calls[0][1][1].startswith("l_german:\n")


def test_batch_continues_after_one_plan_fails(tmp_path):
    first = _extra_plan(tmp_path, "TST_first")
    second = _extra_plan(tmp_path, "TST_second")
    written = []

    def write_texts(entries):
        batch = tuple(entries)
        if batch[0][0] == first.focus_path:
            raise OSError("disk full")
        written.extend(batch)

    results = execute_export_plans([first, second], write_texts)

    assert results[0].error is not None
    assert results[1].ok
    assert [path for path, _text, _encoding in written] == [second.focus_path]


def test_failed_main_plan_preserves_the_atomic_write_group(tmp_path):
    plan = _main_plan(tmp_path)
    calls = []

    def write_texts(entries):
        calls.append(tuple(entries))
        raise OSError("disk full")

    results = execute_export_plans([plan], write_texts)

    assert results[0].error is not None
    assert len(calls) == 1
    assert [path for path, _text, _encoding in calls[0]] == [
        plan.focus_path,
        plan.loc_path,
    ]


def test_batch_reports_progress_for_each_plan(tmp_path):
    plans = [_extra_plan(tmp_path, "TST_one"), _extra_plan(tmp_path, "TST_two")]
    progress = []

    def report(index, total, label):
        progress.append((index, total, label))

    execute_export_plans(plans, lambda _entries: None, progress=report)

    assert progress == [(1, 2, plans[0].label), (2, 2, plans[1].label)]
