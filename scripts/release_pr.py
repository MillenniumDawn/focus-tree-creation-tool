#!/usr/bin/env python3

# Prepares the release commit the release pull request carries: promote the
# changelog's `## Unreleased` section to a version heading and move every
# version source in the repo to match.
#
# Everything that shapes text is a pure function so the tests need no
# repository; main() is the only part that touches disk.

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from versioning import (
    BUMPS,
    REPO_ROOT,
    next_stable_version,
    read_version,
    write_version_sources,
)

UNRELEASED = "## Unreleased"

# Sections are level two, individual changes level three, so only a `## `
# heading ends the Unreleased section.
SECTION_PREFIX = "## "


def unreleased_section(changelog: str) -> list[str]:
    lines = changelog.split("\n")
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().lower() == UNRELEASED.lower()
        ),
        -1,
    )
    if start == -1:
        return []
    rest = lines[start + 1 :]
    end = next(
        (index for index, line in enumerate(rest) if line.startswith(SECTION_PREFIX)),
        len(rest),
    )
    return rest[:end]


def has_release_content(changelog: str) -> bool:
    # The trailing space matters: this changelog separates its sections with
    # `---` rules, which would otherwise read as bullets and make every empty
    # Unreleased section look releasable.
    return any(
        line.lstrip().startswith(("- ", "* ")) for line in unreleased_section(changelog)
    )


def promote_unreleased(changelog: str, version: str, today: dt.date) -> str:
    """Leave an empty `## Unreleased` behind and open a dated version section."""
    heading = f"## [{version}] — {today.isoformat()}"
    lines = changelog.split("\n")
    for index, line in enumerate(lines):
        if line.strip().lower() == UNRELEASED.lower():
            # `---` between level-two sections is this file's own style.
            lines[index : index + 1] = [UNRELEASED, "", "---", "", heading]
            return "\n".join(lines)
    raise RuntimeError(f"CHANGELOG.md has no {UNRELEASED!r} heading to promote")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote the changelog's Unreleased section to a release."
    )
    parser.add_argument("--bump", choices=BUMPS, default="patch")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the version without writing any file",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository to read and rewrite (default: this checkout)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = Path(args.repo_root)
    changelog_path = repo_root / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")

    if not has_release_content(changelog):
        # The push that merges the release pull request itself lands an empty
        # Unreleased section, so this is the workflow's own no-op guard rather
        # than an error.
        print(
            f"No bullets under {UNRELEASED!r} in {changelog_path}; nothing to release.",
            file=sys.stderr,
        )
        print("release=false")
        return 0

    current = read_version((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    version = next_stable_version(current, args.bump)

    if args.dry_run:
        print(f"dry run: would release {current} -> {version}", file=sys.stderr)
    else:
        changelog_path.write_text(
            promote_unreleased(changelog, version, dt.date.today()), encoding="utf-8"
        )
        written = write_version_sources(repo_root, version)
        print(
            f"promoted {UNRELEASED} to {version} and moved {', '.join(written)}",
            file=sys.stderr,
        )
    print("release=true")
    print(f"version={version}")
    print(f"bump={args.bump}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as error:
        sys.stderr.write(f"::error::{error}\n")
        raise SystemExit(1) from error
