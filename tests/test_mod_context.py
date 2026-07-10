"""Tests for hoi4cm.mod.context — the mod-asset scanner.

Each test builds a tiny mod tree under ``tmp_path`` with just the
subdirectories the scanner walks, then verifies the corresponding
``MOD.*`` field was populated correctly. Keeps each test fast and
side-effect-free.
"""

import json
import os
import textwrap
import threading

import pytest

from hoi4cm.mod import MOD
from hoi4cm.mod import context as ctx_mod
from hoi4cm.mod import scan_cache as scan_cache_mod


@pytest.fixture(autouse=True)
def isolate_scan_cache(tmp_path_factory, monkeypatch):
    """Keep the SQLite scan cache out of the real ~/.hoi4cm during tests."""
    monkeypatch.setattr(
        scan_cache_mod, "STATE_DIR", str(tmp_path_factory.mktemp("hoi4cm_state"))
    )


@pytest.fixture
def mod_tree(tmp_path):
    """Create a minimal but realistic mod directory tree."""

    def write(rel, content):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"))
        return path

    write(
        "common/national_focus/usa.txt",
        """
        focus_tree = {
            id = USA_focus_tree
            focus = { id = USA_first_focus }
            focus = { id = USA_second_focus }
        }
        """,
    )
    write(
        "common/ideas/usa_spirits.txt",
        """
        ideas = {
            USA = {
                USA_manifest_destiny = { picture = GFX_idea_usa_md }
                USA_great_depression = { picture = GFX_idea_usa_gd }
            }
        }
        """,
    )
    write(
        "common/decisions/USA.txt",
        """
        USA_intervention_in_china = {
            available = { has_war = no }
        }
        USA_destroy_hitler = {
            available = { threat > 0.5 }
        }
        """,
    )
    write(
        "common/decisions/categories/USA_decision_categories.txt",
        """
        USA_intervention_category = {
            icon = GFX_decision_category_usa_intervention
        }
        """,
    )
    write(
        "common/dynamic_modifiers/USA.txt",
        """
        USA_great_depression_modifier = {
            icon = GFX_idea_usa_great_depression
        }
        """,
    )
    write(
        "common/country_tags/00_countries.txt",
        """
        USA = "countries/United States.txt"
        GER = "countries/Germany.txt"
        SOV = "countries/Soviet Union.txt"
        """,
    )
    write(
        "events/USA_events.txt",
        """
        add_namespace = usa_events
        country_event = {
            id = usa_events.1
            title = usa_events.1.t
        }
        country_event = {
            id = usa_events.2
        }
        """,
    )
    write(
        "common/scripted_effects/00_money_system.txt",
        "## MD money system placeholder\n",
    )
    write(
        "common/scripted_localisation/money_scripted_localization.txt",
        "## MD sloc placeholder\n",
    )
    write(
        "localisation/english/MD_money_l_english.yml",
        "l_english:\n  x: y\n",
    )
    # A single focus goal .dds so the GFX scanner has something to index
    (tmp_path / "gfx" / "interface" / "goals").mkdir(parents=True, exist_ok=True)
    (tmp_path / "gfx" / "interface" / "goals" / "USA_first_focus.dds").write_bytes(b"")

    return tmp_path


def test_scan_loads_sprites(mod_tree):
    MOD.scan(str(mod_tree))
    assert "GFX_focus_USA_first_focus" in MOD.sprites


def test_scan_loads_focus_ids(mod_tree):
    MOD.scan(str(mod_tree))
    assert "USA_first_focus" in MOD.focus_ids
    assert "USA_second_focus" in MOD.focus_ids


def test_scan_loads_idea_ids(mod_tree):
    MOD.scan(str(mod_tree))
    assert "USA_manifest_destiny" in MOD.idea_ids
    assert "USA_great_depression" in MOD.idea_ids


def test_scan_loads_decision_ids_and_categories(mod_tree):
    MOD.scan(str(mod_tree))
    assert "USA_intervention_in_china" in MOD.decision_ids
    assert "USA_destroy_hitler" in MOD.decision_ids
    assert "USA_intervention_category" in MOD.decision_cats
    # Block-keyword false positives are filtered
    assert "category" not in MOD.decision_ids
    assert "available" not in MOD.decision_ids


def test_scan_loads_dyn_mods(mod_tree):
    MOD.scan(str(mod_tree))
    assert "USA_great_depression_modifier" in MOD.dyn_mod_ids


def test_scan_loads_country_tags(mod_tree):
    MOD.scan(str(mod_tree))
    assert MOD.country_tags[:3] == ["USA", "GER", "SOV"]


def test_scan_loads_event_ids(mod_tree):
    MOD.scan(str(mod_tree))
    assert MOD.event_ids.get("USA_events") == ["usa_events.1", "usa_events.2"]


def test_scan_discovers_md_money_files(mod_tree):
    MOD.scan(str(mod_tree))
    assert MOD.md_money_system_file.endswith("00_money_system.txt")
    assert "money_scripted_localization" in MOD.md_money_scripted_loc_file
    assert MOD.md_money_yml_file.endswith("MD_money_l_english.yml")


def test_md_detection_by_name(tmp_path, monkeypatch):
    """A mod named 'Millennium Dawn' is flagged by directory name alone."""
    # Don't let a real user config override our detection
    monkeypatch.setattr(ctx_mod, "cfg_load", lambda: {})
    md_root = tmp_path / "Millennium_Dawn"
    (md_root / "common").mkdir(parents=True)
    (md_root / "descriptor.mod").write_text('name = "Some Other Mod"')
    MOD.scan(str(md_root))
    assert MOD.is_md


def test_md_detection_false_for_normal_mod(mod_tree):
    MOD.scan(str(mod_tree))
    assert not MOD.is_md


def test_summary_includes_counts(mod_tree):
    MOD.scan(str(mod_tree))
    s = MOD.summary()
    # 3 focus IDs: USA_first_focus, USA_second_focus, USA_focus_tree (the tree's own id)
    assert "3 focus IDs" in s
    assert "2 ideas" in s
    assert "1 dyn modifiers" in s
    assert "3 tags" in s


def test_get_image_returns_none_when_pillow_unavailable(monkeypatch, mod_tree):
    """With Pillow disabled, get_image must return None, not crash."""
    monkeypatch.setattr(ctx_mod, "_PIL_OK", False)
    monkeypatch.setattr(ctx_mod, "_PILImage", None)
    monkeypatch.setattr(ctx_mod, "_PILImageTk", None)
    MOD.scan(str(mod_tree))
    assert MOD.get_image("GFX_focus_USA_first_focus") is None


def test_get_image_returns_none_for_unknown_gfx(mod_tree):
    MOD.scan(str(mod_tree))
    assert MOD.get_image("GFX_does_not_exist") is None
    assert any("NOT IN SPRITES" in e for e in MOD._img_errors)


# ── sprite_imgs bounded LRU (phase 8) ───────────────────────────────────────
#
# get_image() memoizes a miss as None keyed by (gfx_name, size) before ever
# touching Pillow, so these can drive the LRU with plain unknown gfx names —
# no real image files or Pillow install needed. Each test restores maxsize
# in a finally so it can't leak into later tests sharing the MOD singleton.


def test_sprite_imgs_is_a_bounded_lru(mod_tree):
    MOD.scan(str(mod_tree))
    orig_maxsize = MOD.sprite_imgs.maxsize
    MOD.sprite_imgs.maxsize = 3
    try:
        for i in range(5):
            MOD.get_image(f"GFX_missing_{i}")
        assert len(MOD.sprite_imgs) == 3
        assert ("GFX_missing_0", (64, 64)) not in MOD.sprite_imgs
        assert ("GFX_missing_1", (64, 64)) not in MOD.sprite_imgs
        assert ("GFX_missing_2", (64, 64)) in MOD.sprite_imgs
        assert ("GFX_missing_3", (64, 64)) in MOD.sprite_imgs
        assert ("GFX_missing_4", (64, 64)) in MOD.sprite_imgs
    finally:
        MOD.sprite_imgs.maxsize = orig_maxsize


def test_get_image_hit_refreshes_lru_recency(mod_tree):
    """Re-requesting an entry protects it from the next eviction."""
    MOD.scan(str(mod_tree))
    orig_maxsize = MOD.sprite_imgs.maxsize
    MOD.sprite_imgs.maxsize = 2
    try:
        MOD.get_image("GFX_missing_a")
        MOD.get_image("GFX_missing_b")
        MOD.get_image("GFX_missing_a")  # touch "a" again; "b" is now oldest
        MOD.get_image("GFX_missing_c")  # over capacity: evicts "b", not "a"
        assert ("GFX_missing_a", (64, 64)) in MOD.sprite_imgs
        assert ("GFX_missing_b", (64, 64)) not in MOD.sprite_imgs
        assert ("GFX_missing_c", (64, 64)) in MOD.sprite_imgs
    finally:
        MOD.sprite_imgs.maxsize = orig_maxsize


def test_get_image_failure_is_memoized_not_retried(mod_tree):
    """A missing gfx name stays memoized as None, not evicted as if unseen."""
    MOD.scan(str(mod_tree))
    assert MOD.get_image("GFX_missing_retry_check") is None
    key = ("GFX_missing_retry_check", (64, 64))
    assert key in MOD.sprite_imgs
    assert MOD.sprite_imgs[key] is None


def test_scan_dedups_ids_across_files(tmp_path):
    """The same focus ID in two files must appear once, in first-seen order."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    (nf / "a.txt").write_text("focus = { id = SHARED }\nfocus = { id = ONLY_A }\n")
    (nf / "b.txt").write_text("focus = { id = SHARED }\nfocus = { id = ONLY_B }\n")
    MOD.scan(str(tmp_path))
    assert MOD.focus_ids.count("SHARED") == 1
    assert {"SHARED", "ONLY_A", "ONLY_B"} <= set(MOD.focus_ids)


def test_scan_loads_variables(tmp_path):
    """set_variable / add_to_variable names are captured from national_focus."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    (nf / "vars.txt").write_text(
        "focus = {\n"
        "  id = X\n"
        "  completion_reward = {\n"
        "    set_variable = { my_money = 5 }\n"
        "    add_to_variable = { my_score = 1 }\n"
        "  }\n"
        "}\n"
    )
    MOD.scan(str(tmp_path))
    assert {"my_money", "my_score"} <= MOD.variables


def test_national_focus_read_once_per_file(mod_tree, monkeypatch):
    """Focus IDs and variables share a single read of each national_focus file.

    Previously _scan_focuses and _scan_variables each walked the directory,
    reading every file twice.
    """
    counts = {}
    orig_read = MOD._read

    def counting_read(path):
        if os.sep + "national_focus" + os.sep in path:
            counts[path] = counts.get(path, 0) + 1
        return orig_read(path)

    monkeypatch.setattr(MOD, "_read", counting_read)
    MOD.scan(str(mod_tree))
    assert counts, "expected at least one national_focus file to be read"
    assert all(n == 1 for n in counts.values()), counts


def test_scan_cache_skips_unchanged_files(tmp_path, monkeypatch):
    """A warm rescan re-reads only files whose (mtime, size) changed."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    a = nf / "a.txt"
    b = nf / "b.txt"
    a.write_text("focus = { id = A1 }\n")
    b.write_text("focus = { id = B1 }\n")
    MOD.scan(str(tmp_path))  # cold: both read and cached
    assert {"A1", "B1"} <= set(MOD.focus_ids)

    reads = []
    orig = MOD._read
    monkeypatch.setattr(MOD, "_read", lambda p: (reads.append(p), orig(p))[1])
    # Change only b.txt — different content (and size) plus a bumped mtime.
    b.write_text("focus = { id = B2 }\nfocus = { id = B3 }\n")
    st = b.stat()
    os.utime(b, (st.st_atime, st.st_mtime + 10))
    MOD.scan(str(tmp_path))

    assert any(p.endswith("b.txt") for p in reads), reads
    assert not any(p.endswith("a.txt") for p in reads), reads
    assert {"A1", "B2", "B3"} <= set(MOD.focus_ids)
    assert "B1" not in MOD.focus_ids


def test_scan_cache_drops_deleted_file_ids(tmp_path):
    """IDs from a removed file must not linger after a rescan."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    (nf / "keep.txt").write_text("focus = { id = KEEP }\n")
    gone = nf / "gone.txt"
    gone.write_text("focus = { id = GONE }\n")
    MOD.scan(str(tmp_path))
    assert "GONE" in MOD.focus_ids
    gone.unlink()
    MOD.scan(str(tmp_path))
    assert "GONE" not in MOD.focus_ids
    assert "KEEP" in MOD.focus_ids


def test_scan_with_cache_disabled_matches(tmp_path):
    """use_cache=False must produce identical results (no DB written)."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    (nf / "a.txt").write_text("focus = { id = A1 }\nfocus = { id = A2 }\n")
    MOD.use_cache = False
    try:
        MOD.scan(str(tmp_path))
    finally:
        MOD.use_cache = True
    assert {"A1", "A2"} <= set(MOD.focus_ids)


# ── GFX unification characterization ──────────────────────────────────────
#
# These pin down the exact merge/precedence rules of the three gfx scanners
# (sprites / idea_sprites / decision_sprites) before they're rebuilt on top
# of one shared interface+gfx walk. Every branch below was chosen to nail
# down one specific rule:
#   - interface/*.gfx entries take precedence over a same-named disk image
#     (last-write in the interface pass, then setdefault for disk images).
#   - only TOP-LEVEL interface/*.gfx files feed sprites/idea_sprites; nested
#     ones (interface/sub/*.gfx) are only visible to decision_sprites, which
#     walks interface/ recursively.
#   - custom_gfx_dirs are indexed after the mod's own ideas dir, so they only
#     fill in names the ideas dir didn't already provide.
#   - the decision-gfx image walk classifies gfx/ images by substring
#     ("decisions", "ideas", "goals"/"focus" => skipped, else).
@pytest.fixture
def gfx_mod_tree(tmp_path):
    """A mod tree exercising every branch of the gfx scanners."""

    def write(rel, content):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"))
        return path

    def touch(rel):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    # Top-level interface/*.gfx — read by all three scanners.
    write(
        "interface/goals.gfx",
        """
        spriteTypes = {
            spriteType = {
                name = "GFX_focus_USA_first_focus"
                texturefile = "gfx/interface/goals/iface_first_focus.dds"
            }
            spriteType = {
                name = "GFX_focus_extra_from_iface"
                texturefile = "gfx/interface/goals/extra.dds"
            }
        }
        """,
    )
    write(
        "interface/ideas.gfx",
        """
        spriteTypes = {
            spriteType = {
                name = "GFX_idea_from_iface"
                texturefile = "gfx/interface/ideas/iface_idea.dds"
            }
        }
        """,
    )
    # Nested interface/*.gfx — only the (recursive) decision scan sees this.
    write(
        "interface/sub/nested.gfx",
        """
        spriteTypes = {
            spriteType = {
                name = "GFX_nested_only"
                texturefile = "gfx/misc/nested.dds"
            }
        }
        """,
    )

    # Disk images.
    touch("gfx/interface/goals/USA_first_focus.dds")
    touch("gfx/interface/ideas/some_idea.dds")
    touch("gfx/decisions/dec1.dds")
    touch("gfx/ideas_extra/somepic.dds")
    touch("gfx/misc/other_pic.dds")

    return tmp_path


def test_gfx_scan_sprites_prefers_interface_over_disk(gfx_mod_tree):
    """interface/*.gfx wins; the disk goals/ walk only fills setdefault gaps."""
    root = str(gfx_mod_tree)
    MOD.scan(root)
    assert MOD.sprites == {
        "GFX_focus_USA_first_focus": os.path.join(
            root, "gfx", "interface", "goals", "iface_first_focus.dds"
        ),
        "GFX_focus_extra_from_iface": os.path.join(
            root, "gfx", "interface", "goals", "extra.dds"
        ),
    }


def test_gfx_scan_idea_sprites_interface_disk_and_custom_dir(gfx_mod_tree):
    """idea_sprites merges interface/*.gfx, the ideas dir, then custom dirs."""
    root = str(gfx_mod_tree)
    custom_dir = gfx_mod_tree / "custom_ideas"
    custom_dir.mkdir()
    (custom_dir / "some_idea.dds").write_bytes(b"")  # collides with ideas dir
    (custom_dir / "custom_only.dds").write_bytes(b"")
    MOD.custom_gfx_dirs = [str(custom_dir)]
    try:
        MOD.scan(root)
    finally:
        MOD.custom_gfx_dirs = []
    assert MOD.idea_sprites == {
        "GFX_idea_from_iface": os.path.join(
            root, "gfx", "interface", "ideas", "iface_idea.dds"
        ),
        "GFX_idea_some_idea": os.path.join(
            root, "gfx", "interface", "ideas", "some_idea.dds"
        ),
        "GFX_idea_custom_only": str(custom_dir / "custom_only.dds"),
    }


def test_gfx_scan_decision_sprites_all_branches(gfx_mod_tree):
    """decision_sprites: recursive interface walk + classified gfx/ image walk."""
    root = str(gfx_mod_tree)
    MOD.scan(root)
    assert MOD.decision_sprites == {
        "GFX_focus_USA_first_focus": os.path.join(
            root, "gfx", "interface", "goals", "iface_first_focus.dds"
        ),
        "GFX_focus_extra_from_iface": os.path.join(
            root, "gfx", "interface", "goals", "extra.dds"
        ),
        "GFX_idea_from_iface": os.path.join(
            root, "gfx", "interface", "ideas", "iface_idea.dds"
        ),
        "GFX_nested_only": os.path.join(root, "gfx", "misc", "nested.dds"),
        "GFX_idea_some_idea": os.path.join(
            root, "gfx", "interface", "ideas", "some_idea.dds"
        ),
        "GFX_decision_dec1": os.path.join(root, "gfx", "decisions", "dec1.dds"),
        "GFX_decision_category_dec1": os.path.join(
            root, "gfx", "decisions", "dec1.dds"
        ),
        "GFX_idea_somepic": os.path.join(root, "gfx", "ideas_extra", "somepic.dds"),
        "GFX_other_pic": os.path.join(root, "gfx", "misc", "other_pic.dds"),
    }


def test_gfx_cache_skips_interface_gfx_reads_when_unchanged(gfx_mod_tree, monkeypatch):
    """A warm rescan with interface/ untouched must not re-read any .gfx file."""
    root = str(gfx_mod_tree)
    MOD.scan(root)  # cold: builds the unified index, writes the sidecar
    first_sprites = dict(MOD.sprites)
    first_idea_sprites = dict(MOD.idea_sprites)
    first_decision_sprites = dict(MOD.decision_sprites)

    reads = []
    orig = MOD._read
    monkeypatch.setattr(MOD, "_read", lambda p: (reads.append(p), orig(p))[1])
    MOD.scan(root)  # warm: sidecar hit should skip parsing interface definitions

    assert not any(p.endswith(".gfx") for p in reads), reads
    assert MOD.sprites == first_sprites
    assert MOD.idea_sprites == first_idea_sprites
    assert MOD.decision_sprites == first_decision_sprites


def test_gfx_cache_invalidates_on_interface_mtime_change(gfx_mod_tree):
    """Editing an interface/*.gfx file must invalidate the sidecar."""
    root = str(gfx_mod_tree)
    MOD.scan(root)
    assert "GFX_focus_extra_from_iface" in MOD.sprites

    goals_gfx = gfx_mod_tree / "interface" / "goals.gfx"
    goals_gfx.write_text(textwrap.dedent("""
            spriteTypes = {
                spriteType = {
                    name = "GFX_focus_added_later"
                    texturefile = "gfx/interface/goals/added_later.dds"
                }
            }
            """).lstrip("\n"))
    st = goals_gfx.stat()
    os.utime(goals_gfx, (st.st_atime, st.st_mtime + 10))

    MOD.scan(root)
    assert "GFX_focus_added_later" in MOD.sprites
    assert "GFX_focus_extra_from_iface" not in MOD.sprites


def test_gfx_cache_invalidates_on_image_tree_change(gfx_mod_tree):
    """Adding a gfx image rebuilds the cache without an interface change."""
    root = str(gfx_mod_tree)
    MOD.scan(root)
    iface_mtime = ctx_mod._iface_dir_mtime(root)

    added_image = gfx_mod_tree / "gfx" / "interface" / "goals" / "added_later.dds"
    added_image.write_bytes(b"")

    assert ctx_mod._iface_dir_mtime(root) == iface_mtime
    MOD.scan(root)
    assert MOD.sprites["GFX_focus_added_later"] == str(added_image)


def test_gfx_cache_version_mismatch_forces_rescan(gfx_mod_tree):
    """An old-schema (or otherwise mismatched) sidecar is discarded, not misread."""
    root = str(gfx_mod_tree)
    MOD.scan(root)
    cache_file = os.path.join(root, ".hoi4cm_gfx_cache.json")
    assert os.path.isfile(cache_file)
    expected_sprites = dict(MOD.sprites)

    with open(cache_file, encoding="utf-8") as f:
        data = json.load(f)
    data["version"] = 1  # simulate a pre-unification / stale-schema sidecar
    data["sprites"]["GFX_focus_bogus"] = "should not survive a version mismatch"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    MOD.scan(root)
    assert MOD.sprites == expected_sprites
    assert "GFX_focus_bogus" not in MOD.sprites


# ── Read/extract overlap in _scan_files_cached ─────────────────────────────


def test_scan_files_cached_preserves_order_with_mixed_hits_and_misses(tmp_path):
    """Result order always follows the input paths list, regardless of which
    entries are cache hits vs. misses (locks down the ordering contract
    across the read/extract-overlap refactor)."""
    names = ["c", "a", "b", "e", "d"]
    paths = []
    for i, name in enumerate(names):
        p = tmp_path / f"{name}.txt"
        p.write_text(f"{name}{i}")
        paths.append(str(p))

    def extract(text):
        return text.strip()

    cache = scan_cache_mod.ScanCache(str(tmp_path))
    MOD._cache = cache
    try:
        # Prime the cache for two files at non-edge positions, so hits and
        # misses are interleaved rather than a clean prefix/suffix split.
        for p in (paths[1], paths[3]):
            st = os.stat(p)
            cache.put("t", p, st.st_mtime, st.st_size, extract(MOD._read(p)))
        cache.commit()

        result = MOD._scan_files_cached("t", paths, extract)
        assert list(result.keys()) == paths
        for p in paths:
            assert result[p] == extract(MOD._read(p))
    finally:
        cache.close()
        MOD._cache = None


def test_scan_files_cached_extracts_off_the_calling_thread(tmp_path):
    """Cache-miss files are read+extracted together on the pool, not read in
    one pass and extracted in a separate serial pass on the caller."""
    names = ("alpha", "bravo", "charlie", "delta")
    paths = {}
    for name in names:
        p = tmp_path / f"{name}.txt"
        p.write_text(name)
        paths[str(p)] = name

    seen_threads = set()

    def extract(text):
        seen_threads.add(threading.current_thread())
        return text.upper()

    assert MOD._cache is None
    result = MOD._scan_files_cached("t2", list(paths), extract)

    assert result == {p: name.upper() for p, name in paths.items()}
    assert seen_threads - {threading.current_thread()}
