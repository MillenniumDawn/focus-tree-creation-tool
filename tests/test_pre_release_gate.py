"""Keep pre-releases from publishing for a commit whose CI run did not pass."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pre-release.yml"


def _job(name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(rf"^  {name}:\n((?: {{4}}.*\n|\n)+)", text, re.MULTILINE)
    assert match is not None, f"pre-release.yml has no {name} job"
    return match.group(1)


def test_publish_needs_the_ci_gate() -> None:
    needs = re.search(r"^    needs: \[([^\]]*)\]$", _job("publish"), re.MULTILINE)

    assert needs is not None
    assert "gate" in [item.strip() for item in needs.group(1).split(",")]


def test_gate_waits_for_the_ci_push_run_of_the_pushed_commit() -> None:
    gate = _job("gate")

    for part in (
        "gh run list",
        "--workflow ci.yml",
        "--branch main",
        "--event push",
        '--commit "$GITHUB_SHA"',
        "gh run watch",
        "--exit-status",
    ):
        assert part in gate
    assert gate.index("gh run list") < gate.index("gh run watch")


def test_gate_is_read_only_and_bounded() -> None:
    gate = _job("gate")

    permissions = re.search(r"^    permissions:\n((?: {6}.*\n)+)", gate, re.MULTILINE)
    assert permissions is not None
    granted = re.findall(r"^ {6}(\w+): (\w+)$", permissions.group(1), re.MULTILINE)
    assert dict(granted) == {"actions": "read", "checks": "read"}
    assert re.search(r"^    timeout-minutes: \d+$", gate, re.MULTILINE)
    # The job checks nothing out, so gh needs both to reach the API.
    assert "GH_TOKEN: ${{ github.token }}" in gate
    assert "GH_REPO: ${{ github.repository }}" in gate


def test_build_stamps_prerelease_version_before_compiling() -> None:
    build = _job("build")
    stamp = "python scripts/versioning.py stamp-prerelease"

    assert stamp in build
    assert build.index(stamp) < build.index("python build/build.py")
