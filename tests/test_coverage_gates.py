"""Keep CI's package and monolith coverage measurements independent."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_coverage_sources_include_the_package_and_monolith():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["tool"]["coverage"]["run"]["source"] == [
        "hoi4cm",
        "hoi4_content_maker",
    ]


def test_ci_measures_both_sources_and_applies_independent_floors():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    full_test_run = re.search(r"xvfb-run -a pytest\s+--cov\b", workflow)
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
    assert int(package_gate.group(1)) >= 67
    assert int(monolith_gate.group(1)) >= 30
