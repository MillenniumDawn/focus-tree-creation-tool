import fnmatch
import os

import pytest

from hoi4cm.mod import discovery


@pytest.mark.parametrize("case_sensitive", [True, False])
def test_script_paths_preserves_direct_listing_policy(tmp_path, case_sensitive):
    for name in ("z.txt", "A.TXT", ".hidden.txt", "ignored.yml"):
        (tmp_path / name).touch()
    nested = tmp_path / "folder.txt"
    nested.mkdir()
    (nested / "nested.txt").touch()
    names = [".hidden.txt", "folder.txt", "z.txt"]
    if not case_sensitive:
        names.append("A.TXT")

    assert discovery.script_paths(str(tmp_path), case_sensitive=case_sensitive) == [
        str(tmp_path / name) for name in sorted(names)
    ]


def test_script_paths_keeps_missing_directory_errors_opt_in(tmp_path):
    missing = str(tmp_path / "missing")

    with pytest.raises(FileNotFoundError):
        discovery.script_paths(missing)
    assert discovery.script_paths(missing, ignore_errors=True) == []


def test_script_paths_keeps_permission_errors_opt_in(tmp_path, monkeypatch):
    error = PermissionError("denied")

    def denied(_directory):
        raise error

    monkeypatch.setattr(discovery.os, "listdir", denied)

    with pytest.raises(PermissionError) as raised:
        discovery.script_paths(str(tmp_path))
    assert raised.value is error
    assert discovery.script_paths(str(tmp_path), ignore_errors=True) == []


def test_glob_script_paths_keeps_platform_matching_and_hidden_policy(tmp_path):
    for name in ("z.txt", "A.TXT", ".hidden.txt", "ignored.yml"):
        (tmp_path / name).touch()
    nested = tmp_path / "folder.txt"
    nested.mkdir()
    (nested / "nested.txt").touch()
    names = ["folder.txt", "z.txt"]
    if fnmatch.fnmatch("A.TXT", "*.txt"):
        names.append("A.TXT")

    assert discovery.glob_script_paths(str(tmp_path)) == [
        str(tmp_path / name) for name in sorted(names)
    ]
    assert discovery.glob_script_paths(str(tmp_path / "missing")) == []


def test_glob_script_paths_keeps_pattern_characters_in_directory(tmp_path):
    literal = tmp_path / "mod[12]"
    literal.mkdir()
    (literal / "literal.txt").touch()
    matching = tmp_path / "mod1"
    matching.mkdir()
    (matching / "matched.txt").touch()

    assert discovery.script_paths(str(literal)) == [str(literal / "literal.txt")]
    assert discovery.glob_script_paths(str(literal)) == [str(matching / "matched.txt")]


@pytest.mark.parametrize("recursive", [True, False])
def test_walk_image_paths_preserves_order_case_and_depth(tmp_path, recursive):
    for name in ("z.tga", ".hidden.DDS", "a.PNG", "ignored.jpg"):
        (tmp_path / name).touch()
    for directory in ("z", "a"):
        child = tmp_path / directory
        child.mkdir()
        (child / "nested.png").touch()
    (tmp_path / "directory.png").mkdir()
    names = [".hidden.DDS", "a.PNG", "z.tga"]
    if recursive:
        names.extend([os.path.join("a", "nested.png"), os.path.join("z", "nested.png")])

    assert discovery.walk_image_paths(str(tmp_path), recursive=recursive) == tuple(
        str(tmp_path / name) for name in names
    )


def test_flat_image_paths_keeps_image_suffixed_directory_entries(tmp_path):
    for name in ("z.tga", ".hidden.DDS", "a.PNG", "ignored.jpg"):
        (tmp_path / name).touch()
    (tmp_path / "directory.png").mkdir()

    assert discovery.flat_image_paths(str(tmp_path)) == tuple(
        str(tmp_path / name)
        for name in (".hidden.DDS", "a.PNG", "directory.png", "z.tga")
    )


def test_image_discovery_preserves_missing_directory_policies(tmp_path):
    missing = str(tmp_path / "missing")

    assert discovery.walk_image_paths(missing) == ()
    with pytest.raises(FileNotFoundError):
        discovery.flat_image_paths(missing)


def test_walkers_keep_glob_and_walk_permission_errors_nonfatal(tmp_path, monkeypatch):
    def denied(_directory):
        raise PermissionError("denied")

    monkeypatch.setattr(discovery.os, "scandir", denied)

    assert discovery.glob_script_paths(str(tmp_path)) == []
    assert discovery.walk_image_paths(str(tmp_path)) == ()


def test_flat_image_paths_propagates_permission_errors(tmp_path, monkeypatch):
    def denied(_directory):
        raise PermissionError("denied")

    monkeypatch.setattr(discovery.os, "listdir", denied)

    with pytest.raises(PermissionError):
        discovery.flat_image_paths(str(tmp_path))
