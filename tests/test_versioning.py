"""Version arithmetic for the release and pre-release channels."""

from __future__ import annotations

from pathlib import Path

import pytest
from versioning import (
    VERSION_SOURCES,
    check_release_tag,
    next_stable_version,
    parse_version,
    prerelease_identity,
    read_version,
    set_badge_version,
    set_dunder_version,
    set_pyproject_version,
    set_windows_version,
    write_version_sources,
)

PYPROJECT = """[project]
name = "hoi4cm"
version = "0.4.1"
requires-python = ">=3.14"

[tool.mypy]
python_version = "3.14"

[tool.black]
target-version = ["py314"]
"""

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(2, 0, 0, 0),
    prodvers=(2, 0, 0, 0),
    mask=0x3f,
  ),
  kids=[
    StringStruct(u'FileVersion',      u'2.0.0.0'),
    StringStruct(u'ProductVersion',   u'2.0.0.0'),
  ]
)
"""

BADGE = "![Version](https://img.shields.io/badge/Version-2.0-gold)\n"


def test_parse_version_rejects_anything_but_three_parts() -> None:
    assert parse_version("0.4.1") == (0, 4, 1)
    with pytest.raises(ValueError):
        parse_version("0.4")


# --- the pre-release channel -------------------------------------------------


def test_prerelease_takes_the_odd_minor_above_stable() -> None:
    env = {"GITHUB_RUN_NUMBER": "42", "GITHUB_RUN_ATTEMPT": "3"}
    assert prerelease_identity(env, "0.4.1") == {
        "version": "0.5.42",
        "tag": "v0.5.42-pre.3",
    }


def test_prerelease_defaults_the_run_attempt_to_one() -> None:
    assert prerelease_identity({"GITHUB_RUN_NUMBER": "7"}, "1.0.2") == {
        "version": "1.1.7",
        "tag": "v1.1.7-pre.1",
    }


def test_prerelease_uses_only_the_numeric_part_of_a_suffixed_base() -> None:
    assert prerelease_identity({"GITHUB_RUN_NUMBER": "7"}, "1.0.2-beta.2") == {
        "version": "1.1.7",
        "tag": "v1.1.7-pre.1",
    }


def test_prerelease_refuses_an_odd_stable_minor() -> None:
    # 0.5.x is the pre-release line for stable 0.4.x, so a project sitting there
    # means a release landed on the wrong line and must not be built on.
    with pytest.raises(RuntimeError, match="even stable minor"):
        prerelease_identity({"GITHUB_RUN_NUMBER": "1"}, "0.5.0")


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"GITHUB_RUN_NUMBER": ""},
        {"GITHUB_RUN_NUMBER": "not-a-number"},
        {"GITHUB_RUN_NUMBER": "0"},
        {"GITHUB_RUN_NUMBER": "-1"},
        {"GITHUB_RUN_NUMBER": "1", "GITHUB_RUN_ATTEMPT": "0"},
        {"GITHUB_RUN_NUMBER": "1", "GITHUB_RUN_ATTEMPT": "nope"},
    ],
)
def test_prerelease_refuses_an_invalid_run_identity(env: dict[str, str]) -> None:
    with pytest.raises(RuntimeError, match="pre-release"):
        prerelease_identity(env, "0.4.1")


# --- the release line --------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "bump", "expected"),
    [
        ("0.4.1", "patch", "0.4.2"),
        ("0.4.9", "patch", "0.4.10"),
        # A minor bump skips the odd line the pre-releases sit on.
        ("0.4.1", "minor", "0.6.0"),
        ("0.4.1", "major", "1.0.0"),
    ],
)
def test_next_stable_version(current: str, bump: str, expected: str) -> None:
    assert next_stable_version(current, bump) == expected


def test_next_stable_version_refuses_to_bump_off_the_pre_release_line() -> None:
    with pytest.raises(RuntimeError, match="pre-release line"):
        next_stable_version("0.5.42", "patch")


def test_next_stable_version_rejects_an_unknown_bump() -> None:
    with pytest.raises(RuntimeError, match="unknown bump"):
        next_stable_version("0.4.1", "sideways")


@pytest.mark.parametrize("tag", ["v0.4.2", "0.4.2", "v.0.4.2"])
def test_check_release_tag_accepts_a_stable_tag(tag: str) -> None:
    # `v.0.4.0` and `v.0.3.0` are real tags in this repo, so the stray dot is
    # tolerated rather than treated as a broken release.
    assert check_release_tag(tag) == "0.4.2"


def test_check_release_tag_rejects_the_pre_release_line() -> None:
    with pytest.raises(RuntimeError, match="odd pre-release line"):
        check_release_tag("v0.5.0")


def test_check_release_tag_rejects_a_suffixed_tag() -> None:
    with pytest.raises(RuntimeError, match="pre-release channel"):
        check_release_tag("v0.5.42-pre.1")


def test_check_release_tag_rejects_a_non_version_tag() -> None:
    with pytest.raises(RuntimeError, match="not a vX.Y.Z release tag"):
        check_release_tag("nightly")


# --- moving every version source --------------------------------------------


def test_read_version_ignores_other_version_keys() -> None:
    assert read_version(PYPROJECT) == "0.4.1"


def test_read_version_reports_a_pyproject_without_one() -> None:
    with pytest.raises(RuntimeError, match="no version"):
        read_version('[project]\nname = "hoi4cm"\n')


def test_set_pyproject_version_leaves_the_other_version_keys_alone() -> None:
    moved = set_pyproject_version(PYPROJECT, "0.4.2")
    assert 'version = "0.4.2"' in moved
    assert 'python_version = "3.14"' in moved
    assert 'target-version = ["py314"]' in moved


def test_set_dunder_version() -> None:
    assert (
        set_dunder_version('__version__ = "0.1.0"\n', "0.4.2")
        == '__version__ = "0.4.2"\n'
    )


def test_set_badge_version() -> None:
    assert "Version-0.4.2-gold" in set_badge_version(BADGE, "0.4.2")


def test_set_windows_version_moves_both_tuples_and_both_strings() -> None:
    moved = set_windows_version(VERSION_INFO, "0.4.2")
    assert moved.count("(0, 4, 2, 0)") == 2
    assert moved.count("u'0.4.2.0'") == 2
    assert "2.0.0.0" not in moved


def test_set_windows_version_reports_a_resource_it_cannot_move() -> None:
    with pytest.raises(RuntimeError, match="two version tuples"):
        set_windows_version("VSVersionInfo()\n", "0.4.2")


def test_write_version_sources_moves_every_source_together(tmp_path: Path) -> None:
    (tmp_path / "src" / "hoi4cm").mkdir(parents=True)
    (tmp_path / "build").mkdir()
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "src" / "hoi4cm" / "__init__.py").write_text(
        '__version__ = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "build" / "version_info.txt").write_text(VERSION_INFO, encoding="utf-8")
    (tmp_path / "README.md").write_text(BADGE, encoding="utf-8")

    written = write_version_sources(tmp_path, "0.4.2")

    assert written == [relative for relative, _ in VERSION_SOURCES]
    assert read_version((tmp_path / "pyproject.toml").read_text(encoding="utf-8")) == (
        "0.4.2"
    )
    assert '__version__ = "0.4.2"' in (
        tmp_path / "src" / "hoi4cm" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "(0, 4, 2, 0)" in (tmp_path / "build" / "version_info.txt").read_text(
        encoding="utf-8"
    )
    assert "Version-0.4.2-gold" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_the_repo_itself_agrees_across_every_version_source() -> None:
    # The whole point of the table is that these four never drift apart again.
    root = Path(__file__).resolve().parent.parent
    version = read_version((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert f'__version__ = "{version}"' in (
        root / "src" / "hoi4cm" / "__init__.py"
    ).read_text(encoding="utf-8")
    major, minor, patch = parse_version(version)
    assert f"({major}, {minor}, {patch}, 0)" in (
        root / "build" / "version_info.txt"
    ).read_text(encoding="utf-8")
    assert f"Version-{version}-gold" in (root / "README.md").read_text(encoding="utf-8")
