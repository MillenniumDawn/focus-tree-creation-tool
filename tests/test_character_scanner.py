"""Character scanner and effect autocomplete coverage."""

import os

import pytest

from hoi4cm.mod import ModContext
from hoi4cm.mod import scan_cache as scan_cache_mod
from hoi4cm.ui.effects_panel import _augment_character_suggestions


@pytest.fixture(autouse=True)
def isolate_scan_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(
        scan_cache_mod, "STATE_DIR", str(tmp_path_factory.mktemp("hoi4cm_state"))
    )


def test_extract_characters_returns_only_direct_root_keys():
    source = """
    characters = {
        ALICE = {
            advisor = {
                idea_token = nested_idea
                portrait = nested_portrait
                role = { nested_role = { } }
                traits = { nested_trait = { } }
            }
        }
        BOB = {
            portraits = { nested_portrait = portrait_value }
        }
    }
    """

    assert ModContext._extract_characters(source) == ["ALICE", "BOB"]


def test_scan_characters_deduplicates_in_file_order_and_resets(tmp_path):
    characters_dir = tmp_path / "common" / "characters"
    characters_dir.mkdir(parents=True)
    (characters_dir / "a.txt").write_text("characters = { ALPHA = { } SHARED = { } }")
    (characters_dir / "b.txt").write_text("characters = { SHARED = { } BETA = { } }")
    context = ModContext()
    context.character_ids = ["STALE"]

    context.scan(str(tmp_path))

    assert context.character_ids == ["ALPHA", "SHARED", "BETA"]

    context.scan(str(tmp_path / "empty"))

    assert context.character_ids == []


def test_scan_characters_uses_file_cache(tmp_path, monkeypatch):
    characters_dir = tmp_path / "common" / "characters"
    characters_dir.mkdir(parents=True)
    character_file = characters_dir / "characters.txt"
    character_file.write_text("characters = { ALPHA = { } }")
    context = ModContext()
    context.scan(str(tmp_path))

    reads = []
    original_read = context._read
    monkeypatch.setattr(
        context,
        "_read",
        lambda path: (reads.append(path), original_read(path))[1],
    )

    context.scan(str(tmp_path))
    assert reads == []

    character_file.write_text("characters = { BETA = { } }")
    stat = character_file.stat()
    os.utime(character_file, (stat.st_atime, stat.st_mtime + 10))
    context.scan(str(tmp_path))

    assert reads == [str(character_file)]
    assert context.character_ids == ["BETA"]


def test_augment_character_suggestions_sorts_only_character_fields():
    base = ["zeta", "alpha"]
    character_ids = ["beta", "alpha"]

    assert _augment_character_suggestions(
        base, "character", loaded=True, character_ids=character_ids
    ) == ["alpha", "beta", "zeta"]
    assert _augment_character_suggestions(
        base, "advisor", loaded=True, character_ids=character_ids
    ) == ["alpha", "beta", "zeta"]
    assert (
        _augment_character_suggestions(
            base, "country", loaded=True, character_ids=character_ids
        )
        is base
    )
    assert (
        _augment_character_suggestions(
            base, "character", loaded=False, character_ids=character_ids
        )
        is base
    )
