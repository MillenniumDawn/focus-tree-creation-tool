"""Tests for the mod-asset scanner.

Each test builds a tiny mod tree under ``tmp_path`` with just the
subdirectories the scanner walks, then verifies the corresponding
index field was populated correctly. Keeps each test fast and
side-effect-free.
"""

import builtins
import os
import sqlite3
import textwrap
import threading
import types
from concurrent.futures import ThreadPoolExecutor

import pytest

from hoi4cm.core.app_config import AppConfig
from hoi4cm.core.paths import read_file
from hoi4cm.mod import scan_cache as scan_cache_mod
from hoi4cm.mod.context import detect_loc_file, find_loc_files
from hoi4cm.mod.index import ModIndex, ScanSettings
from hoi4cm.ui import sprite_images
from hoi4cm.ui.sprite_images import SpriteImageCache


@pytest.fixture
def mod_index():
    return ModIndex()


@pytest.fixture(autouse=True)
def isolate_scan_cache(tmp_path_factory, monkeypatch):
    """Keep the scan cache out of ~/.hoi4cm."""
    monkeypatch.setattr(
        scan_cache_mod, "STATE_DIR", str(tmp_path_factory.mktemp("hoi4cm_state"))
    )
    monkeypatch.setattr(sprite_images, "_PIL_STATE", None)


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
    # A single focus goal .dds so the GFX scanner has something to index
    (tmp_path / "gfx" / "interface" / "goals").mkdir(parents=True, exist_ok=True)
    (tmp_path / "gfx" / "interface" / "goals" / "USA_first_focus.dds").write_bytes(b"")

    return tmp_path


def test_scan_loads_sprites(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert "GFX_focus_USA_first_focus" in mod_index.sprites


def test_scan_loads_focus_ids(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert "USA_first_focus" in mod_index.focus_ids
    assert "USA_second_focus" in mod_index.focus_ids


def test_scan_loads_idea_ids(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert "USA_manifest_destiny" in mod_index.idea_ids
    assert "USA_great_depression" in mod_index.idea_ids


def test_scan_loads_decision_ids_and_categories(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert "USA_intervention_in_china" in mod_index.decision_ids
    assert "USA_destroy_hitler" in mod_index.decision_ids
    assert "USA_intervention_category" in mod_index.decision_cats
    # Block-keyword false positives are filtered
    assert "category" not in mod_index.decision_ids
    assert "available" not in mod_index.decision_ids


def test_scan_loads_dyn_mods(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert "USA_great_depression_modifier" in mod_index.dyn_mod_ids


def test_scan_loads_country_tags(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert mod_index.country_tags[:3] == ["USA", "GER", "SOV"]


def test_scan_loads_event_ids(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert mod_index.event_ids.get("USA_events") == ["usa_events.1", "usa_events.2"]


def test_scan_ignores_unreadable_descriptor(mod_index, tmp_path, monkeypatch):
    """An unreadable descriptor must not abort the rest of the scan."""
    descriptor = tmp_path / "descriptor.mod"
    descriptor.write_text("name = unreadable_descriptor\n")
    original_read = mod_index._read
    monkeypatch.setattr(
        mod_index,
        "_read",
        lambda path: None if path == str(descriptor) else original_read(path),
    )

    mod_index.scan(str(tmp_path))

    assert mod_index.loaded
    assert not mod_index.is_md


def test_scan_discovers_md_money_files(mod_index, tmp_path):
    money = tmp_path / "common" / "scripted_effects" / "00_money_system.txt"
    money.parent.mkdir(parents=True)
    money.write_text("## MD money system placeholder\n")
    sloc = (
        tmp_path
        / "common"
        / "scripted_localisation"
        / "money_scripted_localization.txt"
    )
    sloc.parent.mkdir(parents=True)
    sloc.write_text("## MD sloc placeholder\n")
    yml = tmp_path / "localisation" / "english" / "MD_money_l_english.yml"
    yml.parent.mkdir(parents=True)
    yml.write_text("l_english:\n  x: y\n")

    mod_index.scan(str(tmp_path))

    assert mod_index.is_md
    assert mod_index.md_money_system_file == str(money)
    assert mod_index.md_money_scripted_loc_file == str(sloc)
    assert mod_index.md_money_yml_file == str(yml)


def test_find_loc_files_is_recursive_and_filters_configured_language(tmp_path):
    french = tmp_path / "localisation" / "french" / "nested" / "focuses.yml"
    english = tmp_path / "localisation" / "english" / "focuses.yml"
    french.parent.mkdir(parents=True)
    english.parent.mkdir(parents=True)
    french.write_text("l_french:\n")
    english.write_text("l_english:\n")

    assert find_loc_files(str(tmp_path), language="french") == [str(french)]


def test_find_loc_files_accepts_configured_suffix_outside_standard_dir(tmp_path):
    loc_file = tmp_path / "localisation" / "custom" / "TAG_l_french.yml"
    loc_file.parent.mkdir(parents=True)
    loc_file.write_text("l_french:\n")

    assert find_loc_files(str(tmp_path), language="french") == [str(loc_file)]


def test_detect_loc_file_finds_configured_language_recursively(tmp_path):
    loc_file = (
        tmp_path / "localisation" / "french" / "focuses" / "MD_focus_FRA_l_french.yml"
    )
    loc_file.parent.mkdir(parents=True)
    loc_file.write_text("l_french:\n")
    raw = "focus_tree = { focus = { id = FRA_example } }"

    assert detect_loc_file(str(tmp_path), raw, language="french") == str(loc_file)
    assert detect_loc_file(str(tmp_path), raw) == ""


def test_scan_discovers_configured_language_md_money_file(tmp_path):
    money = tmp_path / "common" / "scripted_effects" / "00_money_system.txt"
    money.parent.mkdir(parents=True)
    money.write_text("scripted_effect = {}\n")
    loc_file = tmp_path / "localisation" / "french" / "MD_money_l_french.yml"
    loc_file.parent.mkdir(parents=True)
    loc_file.write_text("l_french:\n")
    context = ModIndex()

    context.scan(str(tmp_path), ScanSettings(loc_language="french"))

    assert context.md_money_yml_file == str(loc_file)


def test_md_detection_by_name(tmp_path):
    """A mod named 'Millennium Dawn' is flagged by directory name alone."""
    md_root = tmp_path / "Millennium_Dawn"
    (md_root / "common").mkdir(parents=True)
    (md_root / "descriptor.mod").write_text('name = "Some Other Mod"')
    context = ModIndex()
    context.scan(str(md_root))
    assert context.is_md


def test_md_detection_from_money_system(tmp_path):
    money = tmp_path / "common" / "scripted_effects" / "00_money_system.txt"
    money.parent.mkdir(parents=True)
    money.write_text("scripted_effect = {}\n")

    context = ModIndex()
    context.scan(str(tmp_path))

    assert context.is_md


@pytest.mark.parametrize(
    ("legacy_value", "money_file"),
    [(True, False), (False, True)],
)
def test_legacy_md_override_is_ignored(tmp_path, monkeypatch, legacy_value, money_file):
    monkeypatch.setattr(
        "hoi4cm.core.app_config.cfg_load",
        lambda: {"is_md_override": legacy_value},
    )
    if money_file:
        money = tmp_path / "common" / "scripted_effects" / "00_money_system.txt"
        money.parent.mkdir(parents=True)
        money.write_text("scripted_effect = {}\n")

    config = AppConfig.load()
    context = ModIndex()
    context.scan(str(tmp_path), config.scan_settings())

    assert config.md_mode_override is None
    assert context.is_md is money_file


def test_md_detection_false_for_normal_mod(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert not mod_index.is_md
    assert mod_index.md_money_system_file == ""
    assert mod_index.md_money_scripted_loc_file == ""
    assert mod_index.md_money_yml_file == ""


def test_md_money_scan_is_gated_for_normal_mod(tmp_path, monkeypatch):
    context = ModIndex()
    scanned = []
    monkeypatch.setattr(
        context, "_scan_md_money_files", lambda: scanned.append("money")
    )

    context.scan(str(tmp_path))

    assert scanned == []


def test_md_override_wins_over_detection_and_survives_rescans(tmp_path):
    context = ModIndex()
    money = tmp_path / "common" / "scripted_effects" / "00_money_system.txt"
    money.parent.mkdir(parents=True)
    money.write_text("scripted_effect = {}\n")

    context.scan(str(tmp_path), ScanSettings(md_mode_override=False))
    assert not context.is_md
    assert not context.md_money_system_file

    context.scan(str(tmp_path), ScanSettings(md_mode_override=True))
    assert context.is_md
    assert context.md_money_system_file == str(money)

    context.scan(str(tmp_path), ScanSettings(md_mode_override=False))
    assert not context.is_md
    assert not context.md_money_system_file


def test_md_override_persists_across_config_reload(tmp_path, monkeypatch):
    saved = {}
    monkeypatch.setattr("hoi4cm.core.app_config.cfg_load", lambda: dict(saved))
    monkeypatch.setattr(
        "hoi4cm.core.app_config.cfg_save", lambda data: (saved.update(data), True)[1]
    )

    config = AppConfig()
    config.md_mode_override = False
    assert config.save()
    assert saved["md_mode_override"] is False

    money = tmp_path / "common" / "scripted_effects" / "00_money_system.txt"
    money.parent.mkdir(parents=True)
    money.write_text("scripted_effect = {}\n")
    restarted = AppConfig.load()
    context = ModIndex()
    assert restarted.md_mode_override is False
    context.scan(str(tmp_path), restarted.scan_settings())

    assert not context.is_md


def test_summary_includes_counts(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    s = mod_index.summary()
    # 3 focus IDs: USA_first_focus, USA_second_focus, USA_focus_tree (the tree's own id)
    assert "3 focus IDs" in s
    assert "2 ideas" in s
    assert "1 dyn modifiers" in s
    assert "3 tags" in s


class _FakeDecodedImage:
    def convert(self, _mode):
        return self

    def resize(self, _size, _resample):
        return self


class _FakePillowImage:
    LANCZOS = object()

    def __init__(self):
        self.opened = []

    def open(self, path):
        self.opened.append(path)
        return _FakeDecodedImage()


class _FakePillowImageTk:
    def __init__(self):
        self.photo_threads = []

    def PhotoImage(self, image):
        self.photo_threads.append((threading.get_ident(), image))
        return object()


def _install_fake_pillow_import(monkeypatch, barrier=None):
    pillow_image = _FakePillowImage()
    pillow_image_tk = _FakePillowImageTk()
    core_image = types.SimpleNamespace(
        PIL_OK=True, PILImage=pillow_image, PILImageTk=pillow_image_tk
    )
    real_import = builtins.__import__
    import_calls = []

    def fake_import(name, *args, **kwargs):
        if name == "hoi4cm.core.image":
            import_calls.append(threading.get_ident())
            if barrier is not None:
                barrier.wait(timeout=5)
            return core_image
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    return pillow_image, pillow_image_tk, import_calls, core_image


def test_get_image_returns_none_when_pillow_unavailable(
    mod_index, monkeypatch, mod_tree
):
    """With Pillow disabled, get_image must return None, not crash."""
    monkeypatch.setattr(sprite_images, "_PIL_STATE", (False, None, None))
    mod_index.scan(str(mod_tree))
    cache = SpriteImageCache()
    assert cache.get_image(mod_index.sprites, "GFX_focus_USA_first_focus") is None


def test_get_image_lazily_initializes_pillow_and_reuses_cache(
    mod_index, monkeypatch, mod_tree
):
    (
        pillow_image,
        pillow_image_tk,
        import_calls,
        core_image,
    ) = _install_fake_pillow_import(monkeypatch)
    mod_index.scan(str(mod_tree))
    cache = SpriteImageCache()

    first = cache.get_image(mod_index.sprites, "GFX_focus_USA_first_focus")
    second = cache.get_image(mod_index.sprites, "GFX_focus_USA_first_focus")

    assert first is not None
    assert second is first
    assert import_calls == [threading.get_ident()]
    assert pillow_image.opened == [
        str(mod_tree / "gfx" / "interface" / "goals" / "USA_first_focus.dds")
    ]
    assert [thread_id for thread_id, _image in pillow_image_tk.photo_threads] == [
        threading.get_ident()
    ]
    state = sprite_images._get_pillow_state()
    assert state == (True, pillow_image, pillow_image_tk)
    assert state is sprite_images._PIL_STATE
    assert core_image.PILImage is pillow_image


def test_pillow_state_concurrent_initialization_is_atomic(
    mod_index, monkeypatch, mod_tree
):
    barrier = threading.Barrier(2)
    pillow_image, pillow_image_tk, import_calls, _core_image = (
        _install_fake_pillow_import(monkeypatch, barrier)
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(sprite_images._get_pillow_state) for _ in range(2)]
        results = [future.result() for future in futures]

    expected = (True, pillow_image, pillow_image_tk)
    assert results == [expected, expected]
    assert sprite_images._PIL_STATE == expected
    assert len(import_calls) == 2
    assert pillow_image_tk.photo_threads == []

    mod_index.scan(str(mod_tree))
    cache = SpriteImageCache()
    photo = cache.get_image(mod_index.sprites, "GFX_focus_USA_first_focus")
    assert photo is not None
    assert [thread_id for thread_id, _image in pillow_image_tk.photo_threads] == [
        threading.get_ident()
    ]


def test_get_image_returns_none_for_unknown_gfx(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    cache = SpriteImageCache()
    assert cache.get_image(mod_index.sprites, "GFX_does_not_exist") is None
    assert any("NOT IN SPRITES" in e for e in cache.errors)


# get_image() memoizes a miss as None keyed by (gfx_name, size) before ever
# touching Pillow, so these can drive the LRU with plain unknown gfx names.


def test_sprite_imgs_is_a_bounded_lru(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    cache = SpriteImageCache(maxsize=3)
    for i in range(5):
        cache.get_image(mod_index.sprites, f"GFX_missing_{i}")
    assert len(cache.images) == 3
    assert ("GFX_missing_0", (64, 64)) not in cache.images
    assert ("GFX_missing_1", (64, 64)) not in cache.images
    assert ("GFX_missing_2", (64, 64)) in cache.images
    assert ("GFX_missing_3", (64, 64)) in cache.images
    assert ("GFX_missing_4", (64, 64)) in cache.images


def test_get_image_hit_refreshes_lru_recency(mod_index, mod_tree):
    """Re-requesting an entry protects it from the next eviction."""
    mod_index.scan(str(mod_tree))
    cache = SpriteImageCache(maxsize=2)
    cache.get_image(mod_index.sprites, "GFX_missing_a")
    cache.get_image(mod_index.sprites, "GFX_missing_b")
    cache.get_image(mod_index.sprites, "GFX_missing_a")
    cache.get_image(mod_index.sprites, "GFX_missing_c")
    assert ("GFX_missing_a", (64, 64)) in cache.images
    assert ("GFX_missing_b", (64, 64)) not in cache.images
    assert ("GFX_missing_c", (64, 64)) in cache.images


def test_get_image_failure_is_memoized_not_retried(mod_index, mod_tree):
    """A missing gfx name stays memoized as None, not evicted as if unseen."""
    mod_index.scan(str(mod_tree))
    cache = SpriteImageCache()
    assert cache.get_image(mod_index.sprites, "GFX_missing_retry_check") is None
    key = ("GFX_missing_retry_check", (64, 64))
    assert key in cache.images
    assert cache.images[key] is None


def test_note_file_written_evicts_only_the_affected_sprite(mod_index, mod_tree):
    """An incremental graphics update drops just the changed names from the
    decoded-image LRU instead of flushing it wholesale."""
    mod_index.scan(str(mod_tree))
    cache = SpriteImageCache()
    affected_key = ("GFX_focus_USA_first_focus", (64, 64))
    unrelated_key = ("GFX_does_not_exist", (64, 64))
    cache.get_image(mod_index.sprites, affected_key[0])
    cache.get_image(mod_index.sprites, unrelated_key[0])
    assert affected_key in cache.images
    assert unrelated_key in cache.images

    image = mod_tree / "gfx" / "interface" / "goals" / "USA_first_focus.dds"
    image.write_bytes(b"overwritten with more bytes")
    cache.evict(mod_index.note_file_written(str(image)))

    assert affected_key not in cache.images
    assert unrelated_key in cache.images


def test_note_file_written_removes_deleted_sprite_name(mod_index, mod_tree):
    mod_index.scan(str(mod_tree))
    assert "GFX_focus_USA_first_focus" in mod_index.sprites

    image = mod_tree / "gfx" / "interface" / "goals" / "USA_first_focus.dds"
    image.unlink()
    mod_index.note_file_deleted(str(image))

    assert "GFX_focus_USA_first_focus" not in mod_index.sprites


def test_scan_dedups_ids_across_files(mod_index, tmp_path):
    """The same focus ID in two files must appear once, in first-seen order."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    (nf / "a.txt").write_text("focus = { id = SHARED }\nfocus = { id = ONLY_A }\n")
    (nf / "b.txt").write_text("focus = { id = SHARED }\nfocus = { id = ONLY_B }\n")
    mod_index.scan(str(tmp_path))
    assert mod_index.focus_ids.count("SHARED") == 1
    assert {"SHARED", "ONLY_A", "ONLY_B"} <= set(mod_index.focus_ids)


def test_scan_loads_variables(mod_index, tmp_path):
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
    mod_index.scan(str(tmp_path))
    assert {"my_money", "my_score"} <= mod_index.variables


def test_national_focus_read_once_per_file(mod_index, mod_tree, monkeypatch):
    """Focus IDs and variables share a single read of each national_focus file.

    Previously _scan_focuses and _scan_variables each walked the directory,
    reading every file twice.
    """
    counts = {}
    orig_read = mod_index._read

    def counting_read(path):
        if os.sep + "national_focus" + os.sep in path:
            counts[path] = counts.get(path, 0) + 1
        return orig_read(path)

    monkeypatch.setattr(mod_index, "_read", counting_read)
    mod_index.scan(str(mod_tree))
    assert counts, "expected at least one national_focus file to be read"
    assert all(n == 1 for n in counts.values()), counts


def test_scan_cache_skips_unchanged_files(mod_index, tmp_path, monkeypatch):
    """A warm rescan re-reads only files whose (mtime, size) changed."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    a = nf / "a.txt"
    b = nf / "b.txt"
    a.write_text("focus = { id = A1 }\n")
    b.write_text("focus = { id = B1 }\n")
    mod_index.scan(str(tmp_path))  # cold: both read and cached
    assert {"A1", "B1"} <= set(mod_index.focus_ids)

    reads = []
    orig = mod_index._read
    monkeypatch.setattr(mod_index, "_read", lambda p: (reads.append(p), orig(p))[1])
    # Change only b.txt — different content (and size) plus a bumped mtime.
    b.write_text("focus = { id = B2 }\nfocus = { id = B3 }\n")
    st = b.stat()
    os.utime(b, (st.st_atime, st.st_mtime + 10))
    mod_index.scan(str(tmp_path))

    assert any(p.endswith("b.txt") for p in reads), reads
    assert not any(p.endswith("a.txt") for p in reads), reads
    assert {"A1", "B2", "B3"} <= set(mod_index.focus_ids)
    assert "B1" not in mod_index.focus_ids


def test_scan_cache_drops_deleted_file_ids(mod_index, tmp_path):
    """IDs from a removed file must not linger after a rescan."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    (nf / "keep.txt").write_text("focus = { id = KEEP }\n")
    gone = nf / "gone.txt"
    gone.write_text("focus = { id = GONE }\n")
    mod_index.scan(str(tmp_path))
    assert "GONE" in mod_index.focus_ids
    gone.unlink()
    mod_index.scan(str(tmp_path))
    assert "GONE" not in mod_index.focus_ids
    assert "KEEP" in mod_index.focus_ids


def test_scan_with_cache_disabled_matches(mod_index, tmp_path):
    """use_cache=False must produce identical results (no DB written)."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    (nf / "a.txt").write_text("focus = { id = A1 }\nfocus = { id = A2 }\n")
    mod_index.use_cache = False
    try:
        mod_index.scan(str(tmp_path))
    finally:
        mod_index.use_cache = True
    assert {"A1", "A2"} <= set(mod_index.focus_ids)


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


def test_gfx_scan_sprites_prefers_interface_over_disk(mod_index, gfx_mod_tree):
    """interface/*.gfx wins; the disk goals/ walk only fills setdefault gaps."""
    root = str(gfx_mod_tree)
    mod_index.scan(root)
    assert mod_index.sprites == {
        "GFX_focus_USA_first_focus": os.path.join(
            root, "gfx", "interface", "goals", "iface_first_focus.dds"
        ),
        "GFX_focus_extra_from_iface": os.path.join(
            root, "gfx", "interface", "goals", "extra.dds"
        ),
    }


def test_gfx_scan_idea_sprites_interface_disk_and_custom_dir(mod_index, gfx_mod_tree):
    """idea_sprites merges interface/*.gfx, the ideas dir, then custom dirs."""
    root = str(gfx_mod_tree)
    custom_dir = gfx_mod_tree / "custom_ideas"
    custom_dir.mkdir()
    (custom_dir / "some_idea.dds").write_bytes(b"")  # collides with ideas dir
    (custom_dir / "custom_only.dds").write_bytes(b"")
    mod_index.scan(root, ScanSettings(custom_gfx_dirs=(str(custom_dir),)))
    assert mod_index.idea_sprites == {
        "GFX_idea_from_iface": os.path.join(
            root, "gfx", "interface", "ideas", "iface_idea.dds"
        ),
        "GFX_idea_some_idea": os.path.join(
            root, "gfx", "interface", "ideas", "some_idea.dds"
        ),
        "GFX_idea_custom_only": str(custom_dir / "custom_only.dds"),
    }


def test_gfx_scan_decision_sprites_all_branches(mod_index, gfx_mod_tree):
    """decision_sprites: recursive interface walk + classified gfx/ image walk."""
    root = str(gfx_mod_tree)
    mod_index.scan(root)
    assert mod_index.decision_sprites == {
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


def test_gfx_cache_skips_interface_gfx_reads_when_unchanged(
    mod_index, gfx_mod_tree, monkeypatch
):
    """A warm rescan with interface/ untouched must not re-read any .gfx file."""
    root = str(gfx_mod_tree)
    mod_index.scan(root)  # cold: builds the unified index, writes the sidecar
    first_sprites = dict(mod_index.sprites)
    first_idea_sprites = dict(mod_index.idea_sprites)
    first_decision_sprites = dict(mod_index.decision_sprites)

    reads = []
    orig = mod_index._read
    monkeypatch.setattr(mod_index, "_read", lambda p: (reads.append(p), orig(p))[1])
    mod_index.scan(root)  # warm: sidecar hit should skip parsing interface definitions

    assert not any(p.endswith(".gfx") for p in reads), reads
    assert mod_index.sprites == first_sprites
    assert mod_index.idea_sprites == first_idea_sprites
    assert mod_index.decision_sprites == first_decision_sprites


def test_gfx_cache_invalidates_on_interface_mtime_change(mod_index, gfx_mod_tree):
    """Editing an interface/*.gfx file must invalidate the sidecar."""
    root = str(gfx_mod_tree)
    mod_index.scan(root)
    assert "GFX_focus_extra_from_iface" in mod_index.sprites

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

    mod_index.scan(root)
    assert "GFX_focus_added_later" in mod_index.sprites
    assert "GFX_focus_extra_from_iface" not in mod_index.sprites


def test_gfx_cache_invalidates_on_image_tree_change(mod_index, gfx_mod_tree):
    """Adding a gfx image rebuilds the cache without an interface change."""
    root = str(gfx_mod_tree)
    mod_index.scan(root)

    added_image = gfx_mod_tree / "gfx" / "interface" / "goals" / "added_later.dds"
    added_image.write_bytes(b"")

    mod_index.scan(root)
    assert mod_index.sprites["GFX_focus_added_later"] == str(added_image)


def test_gfx_cache_version_mismatch_forces_rescan(mod_index, gfx_mod_tree):
    root = str(gfx_mod_tree)
    mod_index.scan(root)
    expected_sprites = dict(mod_index.sprites)
    database = scan_cache_mod.database_path(root)
    connection = sqlite3.connect(database)
    with connection:
        connection.execute("UPDATE graphics_snapshot SET schema_version = 0")
    connection.close()

    mod_index.scan(root)
    assert mod_index.sprites == expected_sprites


def test_gfx_scan_preserves_dictionary_identity(mod_index, gfx_mod_tree):
    dictionaries = (
        mod_index.sprites,
        mod_index.idea_sprites,
        mod_index.decision_sprites,
    )
    mod_index.scan(str(gfx_mod_tree))
    mod_index.scan(str(gfx_mod_tree))
    assert mod_index.sprites is dictionaries[0]
    assert mod_index.idea_sprites is dictionaries[1]
    assert mod_index.decision_sprites is dictionaries[2]


# ── Read/extract overlap in _scan_files_cached ─────────────────────────────


def test_scan_files_cached_preserves_order_with_mixed_hits_and_misses(
    mod_index, tmp_path
):
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
    mod_index._cache = cache
    try:
        # Prime the cache for two files at non-edge positions, so hits and
        # misses are interleaved rather than a clean prefix/suffix split.
        for p in (paths[1], paths[3]):
            st = os.stat(p)
            cache.put("t", p, st.st_mtime, st.st_size, extract(mod_index._read(p)))
        cache.commit()

        result = mod_index._scan_files_cached("t", paths, extract)
        assert list(result.keys()) == paths
        for p in paths:
            assert result[p] == extract(mod_index._read(p))
    finally:
        cache.close()
        mod_index._cache = None


def test_scan_files_cached_extracts_off_the_calling_thread(mod_index, tmp_path):
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

    assert mod_index._cache is None
    result = mod_index._scan_files_cached("t2", list(paths), extract)

    assert result == {p: name.upper() for p, name in paths.items()}
    assert seen_threads - {threading.current_thread()}


def test_scan_files_cached_single_read_failure_is_retried_not_cached(
    mod_index, tmp_path, monkeypatch
):
    """A failed single-file read has an empty shape but no cache row."""
    path = tmp_path / "retry.txt"
    path.write_text("valid")
    cache = scan_cache_mod.ScanCache(str(tmp_path))
    reads = 0
    original_read = mod_index._read

    def flaky_read(candidate):
        nonlocal reads
        reads += 1
        if reads == 1:
            return None
        return original_read(candidate)

    monkeypatch.setattr(mod_index, "_read", flaky_read)
    mod_index._cache = cache
    try:

        def extract(text):
            return [] if not text else [text]

        first = mod_index._scan_files_cached("retry", [str(path)], extract)
        stat = path.stat()
        assert first == {str(path): []}
        assert cache.get("retry", str(path), stat.st_mtime, stat.st_size) is None

        second = mod_index._scan_files_cached("retry", [str(path)], extract)
        assert second == {str(path): ["valid"]}
        assert cache.get("retry", str(path), stat.st_mtime, stat.st_size) == ["valid"]
        assert reads == 2
    finally:
        cache.close()
        mod_index._cache = None


def test_scan_files_cached_failed_thread_read_keeps_valid_sibling(
    mod_index, tmp_path, monkeypatch
):
    """A pool read failure contributes empty data without dropping siblings."""
    bad = tmp_path / "bad.txt"
    good = tmp_path / "good.txt"
    bad.write_text("unreadable")
    good.write_text("valid")
    original_read = mod_index._read
    seen_threads = set()

    def read(candidate):
        if candidate == str(bad):
            return None
        return original_read(candidate)

    def extract(text):
        seen_threads.add(threading.current_thread())
        return [] if not text else [text]

    monkeypatch.setattr(mod_index, "_read", read)
    result = mod_index._scan_files_cached("siblings", [str(bad), str(good)], extract)

    assert result == {str(bad): [], str(good): ["valid"]}
    assert seen_threads - {threading.current_thread()}


def test_scan_skips_unreadable_file_beside_valid_focus_file(
    mod_index, tmp_path, monkeypatch
):
    """Unreadable focus files do not abort valid focus and variable scans."""
    nf = tmp_path / "common" / "national_focus"
    nf.mkdir(parents=True)
    bad = nf / "bad.txt"
    good = nf / "good.txt"
    bad.write_text("focus = { id = UNREADABLE }")
    good.write_text(
        "focus = {\n"
        "  id = VALID\n"
        "  completion_reward = { set_variable = { score = 1 } }\n"
        "}\n"
    )
    original_read = mod_index._read
    monkeypatch.setattr(
        mod_index,
        "_read",
        lambda path: None if path == str(bad) else original_read(path),
    )
    monkeypatch.setattr(mod_index, "use_cache", False)
    mod_index.scan(str(tmp_path))

    assert "VALID" in mod_index.focus_ids
    assert "UNREADABLE" not in mod_index.focus_ids
    assert "score" in mod_index.variables


def test_scan_skips_oversize_file_beside_valid_event_file(
    mod_index, tmp_path, monkeypatch
):
    """The read limit skips one event file while preserving its sibling."""
    events = tmp_path / "events"
    events.mkdir()
    (events / "oversize.txt").write_text("x" * 100)
    (events / "valid.txt").write_text("country_event = { id = valid.1 }\n")

    def limited_read(path, max_bytes=None):
        return read_file(path, max_bytes=64)

    monkeypatch.setattr("hoi4cm.mod.index.read_file", limited_read)
    monkeypatch.setattr(mod_index, "use_cache", False)
    mod_index.scan(str(tmp_path))

    assert mod_index.event_ids == {"valid": ["valid.1"]}


# ── Scan failures are recorded, not swallowed ──────────────────────────────


def _ideas_tree(tmp_path):
    """Two valid idea files and one nested too deeply for the parser."""
    ideas = tmp_path / "common" / "ideas"
    ideas.mkdir(parents=True)
    (ideas / "a_good.txt").write_text("ideas = { USA = { USA_one = { } } }")
    (ideas / "b_deep.txt").write_text("ideas = { " + "x = { " * 3000)
    (ideas / "c_good.txt").write_text("ideas = { USA = { USA_two = { } } }")
    return ideas


def _raises(exc):
    def fail():
        raise exc

    return fail


def test_scan_records_failed_step_label(mod_index, tmp_path, monkeypatch):
    candidate = mod_index.new_scan_candidate()
    candidate.use_cache = False
    monkeypatch.setattr(candidate, "_scan_events", _raises(OSError("unreadable")))
    candidate.scan(str(tmp_path))

    assert candidate.loaded
    assert candidate.failed_steps == ["Events"]
    assert candidate.unparsable_files == []


def test_scan_records_unparsable_file_and_keeps_its_siblings(mod_index, tmp_path):
    ideas = _ideas_tree(tmp_path)
    candidate = mod_index.new_scan_candidate()
    candidate.scan(str(tmp_path))

    assert candidate.failed_steps == []
    assert candidate.unparsable_files == [str(ideas / "b_deep.txt")]
    assert candidate.idea_ids == ["USA_one", "USA_two"]


def test_unparsable_file_is_not_cached_and_is_reported_again(mod_index, tmp_path):
    ideas = _ideas_tree(tmp_path)
    candidate = mod_index.new_scan_candidate()
    candidate.scan(str(tmp_path))
    candidate.scan(str(tmp_path))

    assert candidate.unparsable_files == [str(ideas / "b_deep.txt")]
    cache = scan_cache_mod.ScanCache(str(tmp_path))
    try:
        for name, cached in (("a_good", True), ("b_deep", False), ("c_good", True)):
            path = ideas / f"{name}.txt"
            stat = path.stat()
            row = cache.get("ideas", str(path), stat.st_mtime, stat.st_size)
            assert (row is not None) is cached
    finally:
        cache.close()


def test_single_unparsable_file_is_reported_and_not_cached(mod_index, tmp_path):
    path = tmp_path / "only.txt"
    path.write_text("content")
    candidate = mod_index.new_scan_candidate()
    cache = scan_cache_mod.ScanCache(str(tmp_path))
    candidate._cache = cache

    def extract(text):
        if text:
            raise ValueError("bad syntax")
        return []

    try:
        result = candidate._scan_files_cached("single", [str(path)], extract)
        stat = path.stat()
        assert result == {str(path): []}
        assert candidate.unparsable_files == [str(path)]
        assert cache.get("single", str(path), stat.st_mtime, stat.st_size) is None
    finally:
        cache.close()


def test_adopt_scan_carries_failed_steps_and_unparsable_files(
    mod_index, tmp_path, monkeypatch
):
    ideas = _ideas_tree(tmp_path)
    candidate = mod_index.new_scan_candidate()
    candidate.use_cache = False
    monkeypatch.setattr(candidate, "_scan_events", _raises(OSError("denied")))
    monkeypatch.setattr(candidate, "_scan_tags", _raises(ValueError("bad tag")))
    candidate.scan(str(tmp_path))
    target = mod_index.new_scan_candidate()

    target.adopt_scan(candidate)

    assert target.failed_steps == ["Events", "Country Tags"]
    assert target.unparsable_files == [str(ideas / "b_deep.txt")]
    assert mod_index.failed_steps is not candidate.failed_steps
    assert mod_index.unparsable_files is not candidate.unparsable_files
