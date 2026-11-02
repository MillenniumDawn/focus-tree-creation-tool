"""Successful mod writes replace one file's live script-ID contribution."""

import os

import pytest

import hoi4_content_maker as app_module
from hoi4cm.mod import scan_cache
from hoi4cm.mod.index import ModIndex, ScanSettings
from hoi4cm.mod.workspace_files import notifying_workspace_files


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache, "STATE_DIR", str(tmp_path / "cache"))


@pytest.mark.parametrize(
    ("folder", "source", "attr", "effect", "field"),
    [
        (
            "common/characters",
            "characters = { %s = {} }",
            "character_ids",
            "recruit_character",
            "character",
        ),
        (
            "common/ideas",
            "ideas = { country = { %s = {} } }",
            "idea_ids",
            "add_ideas",
            "idea_name",
        ),
        ("events", "country_event = { id = %s }", "event_ids", "country_event", "id"),
        (
            "common/national_focus",
            "focus_tree = { focus = { id = %s } }",
            "focus_ids",
            "complete_national_focus",
            "focus_id",
        ),
    ],
)
def test_saved_ids_replace_one_contributor_and_refresh_suggestions(
    tmp_path, monkeypatch, folder, source, attr, effect, field
):
    root = tmp_path / "mod"
    directory = root / folder
    directory.mkdir(parents=True)
    target = directory / "a.txt"
    target.write_text(source % "old.1")
    (directory / "b.txt").write_text(source % "shared.1")
    index = ModIndex()
    index.scan(str(root))
    reads = []
    original_read = index._read
    monkeypatch.setattr(
        index, "_read", lambda path: (reads.append(path), original_read(path))[1]
    )
    writer = notifying_workspace_files(index, root)
    host = app_module.App.__new__(app_module.App)
    host.index = index

    def suggestions():
        return host._get_effect_suggestions(effect, field)

    assert suggestions() == ["old.1", "shared.1"]
    writer.write_text(target, source % "new.1", encoding="utf-8")
    assert suggestions() == ["new.1", "shared.1"]
    writer.write_text(target, "", encoding="utf-8")
    assert suggestions() == ["shared.1"]
    assert reads == [str(target), str(target)]

    fresh = ModIndex()
    fresh.scan(str(root), ScanSettings(use_cache=False))
    assert getattr(index, attr) == getattr(fresh, attr)


def test_save_after_scan_through_symlinked_root_replaces_contribution(tmp_path):
    root = tmp_path / "mod"
    target = root / "common" / "characters" / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("characters = { FIRST = {} }")
    linked = tmp_path / "linked-mod"
    try:
        linked.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    index = ModIndex()
    index.scan(str(linked))
    target.write_text("characters = { SECOND = {} }")
    index.note_file_written(str(linked / "common" / "characters" / "a.txt"))
    assert index.character_ids == ["SECOND"]


@pytest.mark.parametrize("cache_enabled", [True, False])
def test_save_invalidates_same_stamp_persistent_contribution(tmp_path, cache_enabled):
    root = tmp_path / "mod"
    target = root / "common" / "characters" / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("characters = { FIRST = {} }")
    stamp = target.stat()
    candidate = ModIndex()
    candidate.scan(str(root))
    index = ModIndex()
    index.adopt_scan(candidate)
    index.use_cache = cache_enabled
    writer = notifying_workspace_files(index, root)

    writer.write_text(target, "characters = { OTHER = {} }", encoding="utf-8")
    os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert index.character_ids == ["OTHER"]
    reloaded = ModIndex()
    reloaded.scan(str(root))
    assert reloaded.character_ids == ["OTHER"]


def test_deletion_preserves_duplicate_ids_and_updates_variables(tmp_path):
    directory = tmp_path / "common" / "national_focus"
    directory.mkdir(parents=True)
    target = directory / "a.txt"
    target.write_text("id = A\nid = BOTH\nset_variable = { unique = 1 }")
    (directory / "b.txt").write_text("id = BOTH\nset_variable = { shared = 1 }")
    index = ModIndex()
    index.scan(str(tmp_path))

    target.unlink()
    index.note_file_deleted(target)

    assert index.focus_ids == ["BOTH"]
    assert index.variables == {"shared"}
    reloaded = ModIndex()
    reloaded.scan(str(tmp_path))
    assert reloaded.focus_ids == index.focus_ids


def test_failed_and_foreign_writes_leave_loaded_index_unchanged(tmp_path, monkeypatch):
    root = tmp_path / "mod"
    target = root / "common" / "characters" / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("characters = { OLD = {} }")
    index = ModIndex()
    index.scan(str(root))
    writer = notifying_workspace_files(index, root)
    writer.write_text(
        tmp_path / "other" / "common" / "characters" / "a.txt",
        "characters = { FOREIGN = {} }",
        encoding="utf-8",
    )
    assert index.character_ids == ["OLD"]

    def fail_replace(*_args):
        raise OSError("write failed")

    monkeypatch.setattr("hoi4cm.mod.workspace_files.os.replace", fail_replace)
    with pytest.raises(OSError, match="write failed"):
        writer.write_text(target, "characters = { NEW = {} }", encoding="utf-8")
    assert index.character_ids == ["OLD"]


def test_new_file_order_matches_fresh_scan_without_rescanning(tmp_path):
    directory = tmp_path / "common" / "characters"
    directory.mkdir(parents=True)
    (directory / "b.txt").write_text("characters = { B = {} }")
    index = ModIndex()
    index.scan(str(tmp_path))
    writer = notifying_workspace_files(index, tmp_path)

    writer.write_text(
        directory / "a.txt", "characters = { A = {} B = {} }", encoding="utf-8"
    )

    assert index.character_ids == ["A", "B"]


@pytest.mark.parametrize(
    ("folder", "source", "attr"),
    [
        ("decisions", "old_decision = {}", "decision_ids"),
        ("common/decisions", "old_decision = {}", "decision_ids"),
        ("decisions/categories", "old_category = {}", "decision_cats"),
        ("common/decisions/categories", "old_category = {}", "decision_cats"),
        ("common/scripted_effects", "old_effect = {}", "scripted_effect_ids"),
        ("common/scripted_triggers", "old_trigger = {}", "scripted_trigger_ids"),
        ("common/on_actions", "on_actions = { old_hook = {} }", "on_action_ids"),
        ("common/dynamic_modifiers", "old_modifier = {}", "dyn_mod_ids"),
        ("common/country_tags", 'OLD = "countries/test.txt"', "country_tags"),
    ],
)
def test_other_script_domains_match_a_fresh_scan(tmp_path, folder, source, attr):
    directory = tmp_path / folder
    directory.mkdir(parents=True)
    target = directory / "a.txt"
    target.write_text(source)
    index = ModIndex()
    index.scan(str(tmp_path))

    notifying_workspace_files(index, tmp_path).write_text(
        target, source.replace("old", "new").replace("OLD", "NEW"), encoding="utf-8"
    )

    fresh = ModIndex()
    fresh.scan(str(tmp_path), ScanSettings(use_cache=False))
    assert getattr(index, attr) == getattr(fresh, attr)
    assert getattr(index, attr)


def test_symlink_outside_mod_does_not_mutate_script_ids(tmp_path):
    root = tmp_path / "mod"
    directory = root / "common" / "characters"
    directory.mkdir(parents=True)
    foreign = tmp_path / "foreign.txt"
    foreign.write_text("characters = { FOREIGN = {} }")
    target = directory / "a.txt"
    index = ModIndex()
    index.scan(str(root))
    try:
        target.symlink_to(foreign)
    except OSError:
        pytest.skip("symlinks unavailable")

    index.note_file_written(target)

    assert index.character_ids == []
