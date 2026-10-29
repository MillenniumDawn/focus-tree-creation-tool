"""Keep CI's package and monolith coverage measurements independent."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

# Omitted for a reason other than building Tk widgets.
NON_TK_OMITS = {"src/hoi4cm/mod/_cache_permissions.py"}


def test_coverage_sources_include_the_package_and_monolith():
    assert PYPROJECT["tool"]["coverage"]["run"]["source"] == [
        "hoi4cm",
        "hoi4_content_maker",
    ]


def test_only_tk_modules_are_omitted_from_the_package_floor():
    omitted = set(PYPROJECT["tool"]["coverage"]["report"]["omit"])

    for path in sorted(omitted - NON_TK_OMITS):
        source = (ROOT / path).read_text(encoding="utf-8")
        assert re.search(
            r"^\s*(import tkinter|from tkinter)", source, re.MULTILINE
        ), f"{path} is omitted from coverage but does not import tkinter"


def test_ci_measures_both_sources_and_applies_independent_floors():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    full_test_run = re.search(r"run: >\s+pytest\s+--cov\b", workflow)
    assert full_test_run is not None

    package_gate = re.search(
        r"coverage report --include='src/hoi4cm/\*' --fail-under=(\d+)", workflow
    )
    monolith_gate = re.search(
        r"coverage report --include='hoi4_content_maker\.py' --fail-under=(\d+)",
        workflow,
    )
    assert package_gate is not None
    assert monolith_gate is not None
    assert full_test_run.start() < package_gate.start() < monolith_gate.start()
    assert int(package_gate.group(1)) >= 91
    assert int(monolith_gate.group(1)) >= 34
    assert "xvfb-run -a pytest -m tk" in workflow


TK_MEASURED = ("project_sidebar", "focus_editor", "editor_chrome")


def test_ci_collects_tk_coverage_before_the_package_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    smoke = re.search(
        r"run: >\s+xvfb-run -a pytest -m tk\s+"
        + r"\s+".join(rf"--cov=hoi4cm\.ui\.{name}" for name in TK_MEASURED)
        + r"\s+--cov-append\b",
        workflow,
    )

    assert smoke is not None
    assert smoke.start() < workflow.index("Coverage gate (hoi4cm package)")
    omitted = PYPROJECT["tool"]["coverage"]["report"]["omit"]
    for name in TK_MEASURED:
        assert f"src/hoi4cm/ui/{name}.py" not in omitted


def test_windows_runs_the_native_spotlight_smoke():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    windows_job = workflow.split("  windows-permissions:\n", 1)[1].split(
        "\n  build:", 1
    )[0]

    assert "run: pytest -m tk" in windows_job
