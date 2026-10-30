"""Regression coverage for the wizard-shared state and image caches."""

from hoi4cm.wizards._shared import WizardImageCaches, notifying_workspace_files


class FakeMod:
    def __init__(self, *, loaded, root):
        self.loaded = loaded
        self.root = root
        self.written = []

    def note_file_written(self, path):
        self.written.append(path)


def test_write_into_loaded_mod_notifies_catalog(tmp_path):
    mod = FakeMod(loaded=True, root=str(tmp_path))
    files = notifying_workspace_files(mod, str(tmp_path))
    target = tmp_path / "common" / "ideas" / "spirit.txt"

    files.write_text(target, "content", encoding="utf-8")

    assert mod.written == [str(target)]


def test_append_into_loaded_mod_notifies_catalog(tmp_path):
    mod = FakeMod(loaded=True, root=str(tmp_path))
    files = notifying_workspace_files(mod, str(tmp_path))
    target = tmp_path / "note.yml"
    target.write_text("l_english:\n")

    files.append_text(target, ' key: "v"\n', encoding="utf-8-sig")

    assert mod.written == [str(target)]


def test_write_into_other_root_does_not_notify(tmp_path):
    mod = FakeMod(loaded=True, root=str(tmp_path / "mod"))
    other = tmp_path / "elsewhere"
    files = notifying_workspace_files(mod, str(other))

    files.write_text(other / "note.txt", "content", encoding="utf-8")

    assert mod.written == []


def test_unloaded_mod_does_not_notify(tmp_path):
    mod = FakeMod(loaded=False, root="")
    files = notifying_workspace_files(mod, str(tmp_path))

    files.write_text(tmp_path / "note.txt", "content", encoding="utf-8")

    assert mod.written == []


def test_release_matches_caches_by_identity_not_equality():
    """Two empty window caches are equal dicts but different windows."""
    caches = WizardImageCaches()
    first: dict = {}
    second: dict = {}
    caches.register_window_cache(first)
    caches.register_window_cache(second)

    caches.release_window_cache(second)

    assert len(caches.window_caches) == 1
    assert caches.window_caches[0] is first

    # The still-open cache received an image; mod reload invalidates it.
    image = object()
    first["GFX_a"] = image
    caches.clear()
    assert len(caches.window_caches) == 1
    assert caches.window_caches[0] is first
    assert first == {}

    caches.release_window_cache(first)
    assert caches.window_caches == []


def test_release_is_idempotent_for_both_close_orders():
    caches = WizardImageCaches()
    first: dict = {}
    second: dict = {}
    caches.register_window_cache(first)
    caches.register_window_cache(second)

    caches.release_window_cache(first)
    caches.release_window_cache(first)
    assert len(caches.window_caches) == 1
    assert caches.window_caches[0] is second

    caches.release_window_cache(second)
    caches.release_window_cache(second)
    assert caches.window_caches == []

    caches = WizardImageCaches()
    first = {}
    second = {}
    caches.register_window_cache(first)
    caches.register_window_cache(second)

    caches.release_window_cache(second)
    caches.release_window_cache(second)
    assert len(caches.window_caches) == 1
    assert caches.window_caches[0] is first

    caches.release_window_cache(first)
    caches.release_window_cache(first)
    assert caches.window_caches == []


def test_window_cache_release_unregisters_and_empties():
    caches = WizardImageCaches()
    cache: dict = {"k": object()}
    caches.register_window_cache(cache)

    caches.release_window_cache(cache)

    assert caches.window_caches == []
    assert cache == {}


def test_window_cache_release_is_idempotent():
    caches = WizardImageCaches()
    cache: dict = {"k": object()}
    caches.register_window_cache(cache)
    caches.release_window_cache(cache)

    caches.release_window_cache(cache)

    assert caches.window_caches == []
    assert cache == {}


def test_clear_invalidates_every_cache_without_losing_registration():
    caches = WizardImageCaches()
    window_cache: dict = {"k": object()}
    caches.register_window_cache(window_cache)
    caches.event_gfx["GFX_a"] = "/gfx/a.png"
    caches.event_imgsize["/gfx/a.png"] = (64, 64)

    caches.clear()

    assert caches.event_gfx == {}
    assert caches.event_imgsize == {}
    assert caches.window_caches == [window_cache]
    assert window_cache == {}


def test_caches_are_owned_by_one_app_instance():
    first = WizardImageCaches()
    second = WizardImageCaches()
    first.event_gfx["GFX_a"] = "/gfx/a.png"
    first.register_window_cache({})

    second.clear()

    assert first.event_gfx == {"GFX_a": "/gfx/a.png"}
    assert len(first.window_caches) == 1


def test_helper_is_reachable_from_the_mod_package():
    """Non-wizard callers (the monolith's export path, ui/mod_loading) reach
    it from hoi4cm.mod; _shared only re-exports it."""
    from hoi4cm.mod import notifying_workspace_files as canonical

    assert notifying_workspace_files is canonical


def test_empty_mod_root_does_not_notify(tmp_path, monkeypatch):
    """An unset save root must not accidentally match the cwd."""
    monkeypatch.chdir(tmp_path)
    mod = FakeMod(loaded=True, root=str(tmp_path))

    files = notifying_workspace_files(mod, "")
    files.write_text(tmp_path / "note.txt", "content", encoding="utf-8")

    assert mod.written == []
