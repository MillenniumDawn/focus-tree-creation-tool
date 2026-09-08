#!/usr/bin/env python3

# Version arithmetic for the two publishing channels, and the rewrites that keep
# every version source in the repo saying the same thing.
#
# The channels follow VS Code's convention: stable takes the even minors and
# pre-release the odd minor directly above, with the Actions run number as the
# patch. So stable 0.4.1 gives pre-releases 0.5.<run>, and a minor release skips
# the odd line to land on 0.6.0. The version itself stays numeric; only the Git
# tag carries the -pre.<attempt> suffix.
#
# `pyproject.toml` is the single source of truth. Everything here is a pure
# function over strings so the tests need no repository; main() is the only part
# that touches disk.

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

BUMPS = ("patch", "minor", "major")

REPO_ROOT = Path(__file__).resolve().parent.parent

# `^\s*version` will not match `python_version` or `target-version`, so the
# first hit is `[project]`'s own version and no other key can be caught.
PYPROJECT_VERSION_RE = re.compile(r'^(\s*version\s*=\s*")([^"]*)(")', re.MULTILINE)
DUNDER_VERSION_RE = re.compile(r'^(__version__\s*=\s*")([^"]*)(")', re.MULTILINE)
BADGE_VERSION_RE = re.compile(r"(img\.shields\.io/badge/Version-)([^-]*)(-)")
FILEVERS_RE = re.compile(r"^(\s*(?:filevers|prodvers)=\()([^)]*)(\))", re.MULTILINE)
VERSION_STRUCT_RE = re.compile(
    r"(StringStruct\(u'(?:File|Product)Version',\s*u')([^']*)(')"
)


def parse_version(text: str) -> tuple[int, int, int]:
    parts = text.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"not an x.y.z version: {text!r}")
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


def next_stable_version(current: str, bump: str) -> str:
    """The version a release of `bump` size moves to, staying on the even minors."""
    try:
        major, minor, patch = parse_version(current.split("-", maxsplit=1)[0])
    except ValueError as error:
        raise RuntimeError(f"cannot bump {current!r}: not an x.y.z version") from error
    if minor % 2 != 0:
        raise RuntimeError(
            f"cannot bump {current!r}: {major}.{minor} is a pre-release line, "
            "and releases only ever sit on an even minor"
        )
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if bump == "minor":
        # Skip the odd line the pre-releases of this stable version sit on.
        return f"{major}.{minor + 2}.0"
    if bump == "major":
        return f"{major + 1}.0.0"
    raise RuntimeError(f"unknown bump {bump!r}; expected one of {', '.join(BUMPS)}")


def prerelease_identity(env: Mapping[str, str], base: str) -> dict[str, str]:
    """The version and tag the pre-release channel publishes for this run."""
    try:
        run_number = int(env.get("GITHUB_RUN_NUMBER", "").strip())
        run_attempt = int(env.get("GITHUB_RUN_ATTEMPT", "1").strip())
        major, minor, patch = parse_version(base.split("-", maxsplit=1)[0])
    except ValueError as error:
        raise RuntimeError("pre-release version inputs must be integers") from error
    if run_number < 1 or run_attempt < 1:
        raise RuntimeError("pre-release run number and attempt must be positive")
    if minor % 2 != 0:
        raise RuntimeError(
            f"pre-release requires an even stable minor, but the project is at "
            f"{major}.{minor}.{patch}; releases must not land on the odd "
            "pre-release line"
        )
    version = f"{major}.{minor + 1}.{run_number}"
    return {"version": version, "tag": f"v{version}-pre.{run_attempt}"}


def check_release_tag(tag: str) -> str:
    """Return the version a stable release tag carries, or explain why it can't."""
    text = tag.strip().removeprefix("v").removeprefix(".")
    if "-" in text:
        raise RuntimeError(
            f"{tag!r} carries a suffix, so it belongs to the pre-release channel "
            "and must not be published as a release"
        )
    try:
        major, minor, patch = parse_version(text)
    except ValueError as error:
        raise RuntimeError(f"{tag!r} is not a vX.Y.Z release tag") from error
    if minor % 2 != 0:
        raise RuntimeError(
            f"{tag!r} is on the odd pre-release line; releases only ever sit on "
            "an even minor"
        )
    return f"{major}.{minor}.{patch}"


def read_version(pyproject_text: str) -> str:
    match = PYPROJECT_VERSION_RE.search(pyproject_text)
    if match is None:
        raise RuntimeError("pyproject.toml has no version to read")
    return match.group(2)


def _replace_first(pattern: re.Pattern[str], text: str, value: str, what: str) -> str:
    replaced, count = pattern.subn(
        lambda m: f"{m.group(1)}{value}{m.group(3)}", text, 1
    )
    if count == 0:
        raise RuntimeError(f"found no {what} to move to {value}")
    return replaced


def set_pyproject_version(text: str, version: str) -> str:
    return _replace_first(PYPROJECT_VERSION_RE, text, version, "pyproject.toml version")


def set_dunder_version(text: str, version: str) -> str:
    return _replace_first(DUNDER_VERSION_RE, text, version, "__version__")


def set_badge_version(text: str, version: str) -> str:
    return _replace_first(BADGE_VERSION_RE, text, version, "README version badge")


def set_windows_version(text: str, version: str) -> str:
    """Move both tuples and both strings in the Windows VERSIONINFO resource."""
    major, minor, patch = parse_version(version)
    tuple_text = f"{major}, {minor}, {patch}, 0"
    replaced, tuples = FILEVERS_RE.subn(
        lambda m: f"{m.group(1)}{tuple_text}{m.group(3)}", text
    )
    replaced, structs = VERSION_STRUCT_RE.subn(
        lambda m: f"{m.group(1)}{major}.{minor}.{patch}.0{m.group(3)}", replaced
    )
    if tuples != 2 or structs != 2:
        raise RuntimeError(
            "version_info.txt should carry two version tuples and two version "
            f"strings, found {tuples} and {structs}"
        )
    return replaced


# Every file that states the version, and the rewrite that moves it. Keeping
# them in one table is what stops a new source drifting away unnoticed again.
VERSION_SOURCES: tuple[tuple[str, Callable[[str, str], str]], ...] = (
    ("pyproject.toml", set_pyproject_version),
    ("src/hoi4cm/__init__.py", set_dunder_version),
    ("build/version_info.txt", set_windows_version),
    ("README.md", set_badge_version),
)


def write_version_sources(repo_root: Path, version: str) -> list[str]:
    """Move every version source to `version`, returning the paths written."""
    written = []
    for relative, setter in VERSION_SOURCES:
        path = repo_root / relative
        text = path.read_text(encoding="utf-8")
        moved = setter(text, version)
        if moved != text:
            path.write_text(moved, encoding="utf-8")
        written.append(relative)
    return written


def project_version(repo_root: Path = REPO_ROOT) -> str:
    return read_version((repo_root / "pyproject.toml").read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else ""
    if command == "prerelease-identity":
        identity = prerelease_identity(os.environ, project_version())
        print(f"version={identity['version']}")
        print(f"tag={identity['tag']}")
    elif command == "project-version":
        print(f"version={project_version()}")
    elif command == "next-version":
        bump = args[1] if len(args) > 1 else "patch"
        print(f"version={next_stable_version(project_version(), bump)}")
    elif command == "check-release-tag":
        if len(args) < 2:
            raise RuntimeError("check-release-tag needs a tag")
        print(f"version={check_release_tag(args[1])}")
    else:
        raise RuntimeError(
            "expected one of prerelease-identity, project-version, next-version, "
            "check-release-tag"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as error:
        sys.stderr.write(f"::error::{error}\n")
        raise SystemExit(1) from error
