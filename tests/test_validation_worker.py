import os
import threading
from types import SimpleNamespace

import pytest

import hoi4_content_maker as m
import hoi4cm.focus_tree.validate as validate_mod
from hoi4cm.focus_tree.validate import (
    ValidationSnapshot,
    capture_validation_snapshot,
    collect_loc_keys_from_file,
    validate_document,
)
from hoi4cm.models import Focus, FocusDocument
from hoi4cm.ui.lifecycle import ApplicationLifecycle


@pytest.fixture(autouse=True)
def _mod_loc_file_reset(monkeypatch):
    monkeypatch.setattr(m.MOD, "edit_loc_file", "")


def _focus(
    sid, name=None, x=0, y=0, gfx="GFX_test", effects=(), prereqs=(), tree_idx=0
):
    focus = Focus(x, y)
    focus.id = sid
    focus.name = name or f"focus_{sid}"
    focus.gfx = gfx
    focus.effects = list(effects)
    focus.prereqs = [list(group) for group in prereqs]
    focus.tree_idx = tree_idx
    return focus


def _tree_doc():
    a = _focus(1, name="A", effects=[{"type": "dummy", "fields": {}}])
    b = _focus(
        2,
        name="B",
        x=1,
        effects=[{"type": "dummy", "fields": {}}],
        prereqs=[[1]],
    )
    return FocusDocument([a, b])


def test_snapshot_validation_matches_document_validation():
    doc = _tree_doc()
    doc[1].mutex = [2]
    doc[1].relative_position_id = "A"
    doc[2].relative_position_id = "A"

    assert validate_document(capture_validation_snapshot(doc)) == validate_document(doc)


def test_snapshot_is_detached_from_live_document():
    doc = _tree_doc()
    a, b = doc[1], doc[2]
    expected = validate_document(doc, sprites={"GFX_test": "/a"})
    snapshot = capture_validation_snapshot(doc)

    doc.move(2, 9, 9)
    a.name = "Renamed"
    a.mutex.append(999)
    a.relative_position_id = "Missing"
    doc.set_tree(1, 1)
    b.gfx = "GFX_swapped"
    b.prereqs[0].append(999)
    b.prereqs.append([888])
    b.effects.append({"type": "late"})
    a.effects.clear()
    c = _focus(3, name="C")
    doc[c.id] = c
    del doc[2]

    assert validate_document(snapshot, sprites={"GFX_test": "/a"}) == expected
    assert snapshot[1].name == "A"
    assert snapshot[2].name == "B"
    assert snapshot[2].gfx == "GFX_test"
    assert snapshot[2].prereqs == ((1,),)
    assert snapshot[1].mutex == ()
    assert snapshot[1].relative_position_id is None
    assert snapshot[1].tree_idx == 0
    assert snapshot[2].effects
    assert snapshot[1].effects
    assert set(snapshot) == {1, 2}


def test_snapshot_preserves_occupied_positions_detached():
    doc = FocusDocument([_focus(1, name="A", x=0, y=0), _focus(2, name="B", x=0, y=0)])

    snapshot = capture_validation_snapshot(doc)

    assert snapshot.occupied_positions == {(0, 0): frozenset({1, 2})}
    assert snapshot.occupied_positions is not doc.occupied_positions
    doc.move(2, 3, 3)
    assert snapshot.occupied_positions == {(0, 0): frozenset({1, 2})}
    collisions = [
        issue
        for issue in validate_document(snapshot)
        if issue.code == "position_collision"
    ]
    assert len(collisions) == 1


def test_snapshot_collision_follows_tree_grouping():
    doc = FocusDocument(
        [
            _focus(1, name="A", x=0, y=0),
            _focus(2, name="B", x=0, y=0),
            _focus(3, name="C", x=0, y=0, tree_idx=1),
        ]
    )

    collisions = [
        issue
        for issue in validate_document(capture_validation_snapshot(doc))
        if issue.code == "position_collision"
    ]

    assert len(collisions) == 1
    assert "A" in collisions[0].message and "B" in collisions[0].message
    assert "C" not in collisions[0].message


def test_snapshot_trusts_occupied_positions_over_raw_coords():
    a = _focus(1, name="A", x=0, y=0)
    b = _focus(2, name="B", x=0, y=0)
    doc = FocusDocument([a, b])
    a.x = 7
    snapshot = capture_validation_snapshot(doc)

    assert not any(
        issue.code == "position_collision" for issue in validate_document({1: a, 2: b})
    )
    assert any(
        issue.code == "position_collision" for issue in validate_document(snapshot)
    )
    assert validate_document(snapshot) == validate_document(doc)


def test_snapshot_accepts_plain_mapping_without_index():
    a = _focus(1, name="A", x=0, y=0)
    b = _focus(2, name="B", x=0, y=0)

    snapshot = capture_validation_snapshot({1: a, 2: b})
    a.x = 7

    assert snapshot.occupied_positions is None
    assert not any(
        issue.code == "position_collision" for issue in validate_document({1: a, 2: b})
    )
    assert any(
        issue.code == "position_collision" for issue in validate_document(snapshot)
    )


def test_collect_loc_keys_from_file_missing_or_absent_returns_none(tmp_path):
    assert collect_loc_keys_from_file("") is None
    assert collect_loc_keys_from_file(None) is None
    assert collect_loc_keys_from_file(str(tmp_path / "missing.yml")) is None
    assert collect_loc_keys_from_file(str(tmp_path)) is None


def test_collect_loc_keys_from_file_existing(tmp_path):
    empty = tmp_path / "empty.yml"
    empty.write_text("", encoding="utf-8")
    filled = tmp_path / "l_english.yml"
    filled.write_text('l_english:\n A: "a"\n B:1 "b"\n', encoding="utf-8")

    assert collect_loc_keys_from_file(str(empty)) == set()
    assert collect_loc_keys_from_file(str(filled)) == {"A", "B"}


def test_collect_loc_keys_from_file_unreadable_skips_checks(monkeypatch, tmp_path):
    loc_file = tmp_path / "unreadable.yml"
    loc_file.write_text("l_english:", encoding="utf-8")
    monkeypatch.setattr(
        validate_mod, "read_file_with_encoding", lambda _path: (None, None)
    )

    assert collect_loc_keys_from_file(str(loc_file)) is None


def test_collect_loc_keys_from_file_disappearing_during_read_skips_checks(
    monkeypatch, tmp_path
):
    loc_file = tmp_path / "removed.yml"
    loc_file.write_text("l_english:", encoding="utf-8")
    real_read = validate_mod.read_file_with_encoding

    def disappearing_read(path):
        loc_file.unlink()
        return real_read(path)

    monkeypatch.setattr(validate_mod, "read_file_with_encoding", disappearing_read)

    assert collect_loc_keys_from_file(str(loc_file)) is None


def _fake_host(focuses):
    host = SimpleNamespace(
        focuses=focuses,
        _validation_job=None,
        _lifecycle=SimpleNamespace(begin=lambda scope: None),
        _validation_sprites=lambda: None,
        _apply_validation_result=lambda _issues: None,
    )
    host._run_validation = m.App._run_validation.__get__(host)
    return host


def test_run_validation_reads_loc_only_inside_worker(monkeypatch, tmp_path):
    loc_file = tmp_path / "l_english.yml"
    loc_file.write_text(
        'l_english:\n A: "Alpha"\n A_desc: "d"\n B: "Beta"\n', encoding="utf-8"
    )
    monkeypatch.setattr(m.MOD, "edit_loc_file", str(loc_file))
    doc = _tree_doc()
    expected = validate_document(
        capture_validation_snapshot(doc),
        loc_keys=collect_loc_keys_from_file(str(loc_file)),
    )
    assert [issue.code for issue in expected] == ["loc_missing_desc"]

    io_calls = []
    real_isfile = os.path.isfile
    real_read_file = validate_mod.read_file_with_encoding

    def spy_isfile(path):
        io_calls.append(f"isfile:{path}")
        return real_isfile(path)

    def spy_read_file(path, **kwargs):
        io_calls.append(f"read:{path}")
        return real_read_file(path, **kwargs)

    monkeypatch.setattr(os.path, "isfile", spy_isfile)
    monkeypatch.setattr(validate_mod, "read_file_with_encoding", spy_read_file)
    dispatched = []

    def fake_run_bg(_widget, work, _on_done, **kwargs):
        dispatched.append((work, kwargs))

    monkeypatch.setattr(m, "run_bg", fake_run_bg)
    _fake_host(doc)._run_validation()

    assert io_calls == []
    assert dispatched[0][1].get("scope") == "validation"
    doc.move(2, 5, 5)
    doc[1].name = "Renamed"
    doc[1].prereqs.append([999])
    monkeypatch.setattr(m.MOD, "edit_loc_file", str(tmp_path / "other.yml"))
    assert dispatched[0][0]() == expected
    assert io_calls == [f"read:{loc_file}"]


def test_run_validation_missing_loc_file_skips_loc_checks(monkeypatch, tmp_path):
    monkeypatch.setattr(m.MOD, "edit_loc_file", str(tmp_path / "nope.yml"))
    dispatched = []

    def fake_run_bg(_widget, work, _on_done, **_kwargs):
        dispatched.append(work)

    monkeypatch.setattr(m, "run_bg", fake_run_bg)
    _fake_host(_tree_doc())._run_validation()

    issues = dispatched[0]()
    assert not any(issue.code.startswith("loc_missing") for issue in issues)


def test_run_validation_dispatches_snapshot_with_occupied_positions(monkeypatch):
    doc = FocusDocument([_focus(1, name="A", x=0, y=0), _focus(2, name="B", x=0, y=0)])
    captured = []
    dispatched = []

    def fake_validate(doc_arg, **_kwargs):
        captured.append(doc_arg)
        return []

    def fake_run_bg(_widget, work, _on_done, **_kwargs):
        dispatched.append(work)

    monkeypatch.setattr(m, "validate_document", fake_validate)
    monkeypatch.setattr(m, "run_bg", fake_run_bg)
    _fake_host(doc)._run_validation()
    dispatched[0]()

    assert isinstance(captured[0], ValidationSnapshot)
    assert captured[0].occupied_positions == {(0, 0): frozenset({1, 2})}


class _ValidationHost:
    def __init__(self, focuses):
        self.master = None
        self.focuses = focuses
        self._validation_job = None
        self._validation_issues = []
        self._validation_worst = {}
        self._validation_win = None
        self._lifecycle = ApplicationLifecycle(None)
        self.after_callbacks = []
        self.after_count = 0
        self.applied = []
        self._run_validation = m.App._run_validation.__get__(self)

    def winfo_exists(self):
        return True

    def after(self, delay, fn):
        self.after_count += 1
        self.after_callbacks.append(fn)
        return f"job-{self.after_count}"

    def after_cancel(self, job):
        return None

    def _validation_sprites(self):
        return None

    def _apply_validation_result(self, issues):
        self.applied.append(issues)


def test_stale_validation_result_never_reaches_apply(monkeypatch):
    doc = FocusDocument(
        [
            _focus(1, name="A", x=0, y=0, effects=[{"type": "dummy"}]),
            _focus(2, name="B", x=0, y=0, effects=[{"type": "dummy"}]),
        ]
    )
    host = _ValidationHost(doc)
    try:
        futures = []
        real_run_bg = m.run_bg

        def capturing_run_bg(widget, work, on_done, **kwargs):
            future = real_run_bg(widget, work, on_done, **kwargs)
            futures.append(future)
            return future

        monkeypatch.setattr(m, "run_bg", capturing_run_bg)
        started = threading.Event()
        release_first = threading.Event()
        real_validate = validate_mod.validate_document
        validate_calls = []

        def gated_validate(doc_arg, **kwargs):
            validate_calls.append(doc_arg)
            if len(validate_calls) == 1:
                started.set()
                assert release_first.wait(timeout=5)
            return real_validate(doc_arg, **kwargs)

        monkeypatch.setattr(m, "validate_document", gated_validate)
        host._run_validation()
        assert started.wait(timeout=5)
        doc.move(2, 5, 5, allow_occupied=True)
        host._run_validation()
        release_first.set()
        futures[0].result(timeout=5)
        futures[1].result(timeout=5)
        assert len(validate_calls) == 2
        assert [issue.code for issue in real_validate(validate_calls[0])] == [
            "position_collision"
        ]
        assert validate_document(validate_calls[1]) == []

        for callback in list(host.after_callbacks):
            callback()

        assert host.applied == [[]]
        assert len(host.after_callbacks) == 2
    finally:
        host._lifecycle.close()
