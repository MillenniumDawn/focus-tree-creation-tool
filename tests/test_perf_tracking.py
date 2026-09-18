"""Smoke coverage for the perf tracking harness.

Deliberately tiny: the heavy timing lives in ``scripts/track_perf.py`` and
stays out of the default suite. These tests pin the report schema and the
determinism of the synthetic workloads, not the numbers.
"""

import json

import track_perf

from hoi4cm.perf import AREAS, focus_tree_text, run_all, run_area

EXPECTED_AREAS = (
    "parse",
    "build",
    "batch_load",
    "undo",
    "graphics_scan",
    "scene",
    "export",
)


def test_tracked_areas_match_documented_set():
    assert tuple(AREAS) == EXPECTED_AREAS


def test_run_all_tiny_reports_every_area_with_schema():
    report = run_all(preset="tiny")
    assert [r.area for r in report.results] == list(EXPECTED_AREAS)
    for result in report.results:
        assert result.repeats == 2
        assert result.median_ms >= 0
        assert result.min_ms <= result.median_ms <= result.max_ms
        assert isinstance(result.workload, dict) and result.workload
        assert isinstance(result.extra, dict)


def test_run_area_subset_and_unknown_area():
    report = run_all(areas=["parse"], preset="tiny")
    assert [r.area for r in report.results] == ["parse"]
    assert report.results[0].workload["focuses"] == 12
    try:
        run_area("nope", preset="tiny")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown area")


def test_synthetic_workloads_are_deterministic():
    assert focus_tree_text(12) == focus_tree_text(12)
    first = run_area("parse", preset="tiny")
    second = run_area("parse", preset="tiny")
    assert first.workload == second.workload


def test_report_json_roundtrip_has_expected_keys():
    payload = json.loads(run_all(areas=["build"], preset="tiny").to_json())
    assert payload["tool"] == "track_perf"
    assert payload["preset"] == "tiny"
    assert payload["python"] and payload["platform"]
    (entry,) = payload["areas"]
    assert entry["area"] == "build"
    assert {"median_ms", "min_ms", "max_ms", "workload", "extra"} <= set(entry)


def test_cli_writes_report_file(tmp_path):
    out = tmp_path / "perf.json"
    assert (
        track_perf.main(
            [
                "--areas",
                "parse",
                "--preset",
                "tiny",
                "--repeats",
                "1",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [a["area"] for a in payload["areas"]] == ["parse"]


def test_cli_rejects_unknown_area():
    assert track_perf.main(["--areas", "nope", "--preset", "tiny"]) == 2
