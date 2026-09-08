"""Promoting the changelog's Unreleased section into a release commit."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from release_pr import (
    has_release_content,
    main,
    promote_unreleased,
    unreleased_section,
)
from test_versioning import BADGE, PYPROJECT, VERSION_INFO

CHANGELOG = """# HOI4 Content Maker — Changelog

---

## Unreleased

### Something landed (issue #1)

**[ENHANCEMENT] It does the thing**

- A bullet.

---

## Application Modernization — Python Floor Raised to 3.14

- An older note.
"""

EMPTY_CHANGELOG = """# HOI4 Content Maker — Changelog

---

## Unreleased

---

## [0.4.1] — 2026-09-02

- Already shipped.
"""


def seed(root: Path, changelog: str) -> None:
    (root / "src" / "hoi4cm").mkdir(parents=True)
    (root / "build").mkdir()
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "src" / "hoi4cm" / "__init__.py").write_text(
        '__version__ = "0.4.1"\n', encoding="utf-8"
    )
    (root / "build" / "version_info.txt").write_text(VERSION_INFO, encoding="utf-8")
    (root / "README.md").write_text(BADGE, encoding="utf-8")


def test_unreleased_section_stops_at_the_next_section() -> None:
    section = unreleased_section(CHANGELOG)
    assert "- A bullet." in section
    assert "- An older note." not in section
    # A level-three heading belongs to the section; a level-two one ends it.
    assert "### Something landed (issue #1)" in section


def test_unreleased_section_is_empty_without_the_heading() -> None:
    assert unreleased_section("# Title\n\n## [0.4.1] — 2026-09-02\n") == []


def test_has_release_content() -> None:
    assert has_release_content(CHANGELOG) is True
    assert has_release_content(EMPTY_CHANGELOG) is False


def test_promote_unreleased_dates_the_new_section_and_keeps_unreleased() -> None:
    promoted = promote_unreleased(CHANGELOG, "0.4.2", dt.date(2026, 9, 8))
    assert "## Unreleased\n\n---\n\n## [0.4.2] — 2026-09-08\n" in promoted
    # The bullets stay where they were, now under the version heading.
    assert promoted.index("## [0.4.2]") < promoted.index("- A bullet.")
    assert "## Application Modernization" in promoted


def test_promote_unreleased_reports_a_changelog_without_the_heading() -> None:
    with pytest.raises(RuntimeError, match="no '## Unreleased' heading"):
        promote_unreleased(
            "# Title\n\n## [0.4.1] — 2026-09-02\n", "0.4.2", dt.date.today()
        )


def test_main_promotes_and_moves_every_version_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(tmp_path, CHANGELOG)

    assert main(["--repo-root", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "release=true" in out
    assert "version=0.4.2" in out
    assert "bump=patch" in out
    assert "## [0.4.2] — " in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert 'version = "0.4.2"' in (tmp_path / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "Version-0.4.2-gold" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_main_skips_the_odd_pre_release_line_on_a_minor_bump(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(tmp_path, CHANGELOG)

    assert main(["--repo-root", str(tmp_path), "--bump", "minor"]) == 0

    assert "version=0.6.0" in capsys.readouterr().out


def test_main_reports_nothing_to_release_without_bullets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The merge of the release pull request lands an empty Unreleased section,
    # so this is a no-op rather than a failure.
    seed(tmp_path, EMPTY_CHANGELOG)

    assert main(["--repo-root", str(tmp_path)]) == 0

    captured = capsys.readouterr()
    assert "release=false" in captured.out
    assert "version=" not in captured.out
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == EMPTY_CHANGELOG


def test_main_dry_run_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(tmp_path, CHANGELOG)

    assert main(["--repo-root", str(tmp_path), "--dry-run"]) == 0

    assert "version=0.4.2" in capsys.readouterr().out
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG
    assert 'version = "0.4.1"' in (tmp_path / "pyproject.toml").read_text(
        encoding="utf-8"
    )
