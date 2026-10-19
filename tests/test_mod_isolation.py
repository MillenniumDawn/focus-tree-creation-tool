"""Regression coverage for the opt-in MOD state snapshot."""

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from conftest import _capture_mod_state, _restore_mod_state

from hoi4cm.mod import MOD


def test_mod_snapshot_restores_attributes_containers_catalog_and_image_identity(
    mod_state_isolation,
):
    catalog = MOD.graphics_catalog
    images = MOD.sprite_imgs
    root = MOD.root
    image = object()
    MOD.sprite_imgs["sentinel"] = image
    MOD.event_ids["nested"] = [1, 2]
    MOD.failed_steps.append("before")
    MOD.unparsable_files.append("before.txt")
    snapshot = _capture_mod_state(MOD)

    MOD.__dict__["added_test_attribute"] = True
    del MOD.root
    del MOD.event_ids["nested"][0]
    MOD.event_ids["nested"].append(3)
    MOD.failed_steps.append("after")
    MOD.unparsable_files.append("after.txt")
    MOD.graphics_catalog = type(catalog)()
    MOD.sprite_imgs.clear()

    _restore_mod_state(MOD, snapshot)

    assert not hasattr(MOD, "added_test_attribute")
    assert MOD.root == root
    assert MOD.event_ids["nested"] == [1, 2]
    assert MOD.failed_steps[-1] == "before"
    assert MOD.unparsable_files[-1] == "before.txt"
    assert MOD.graphics_catalog is catalog
    assert MOD.sprite_imgs is images
    assert MOD.sprite_imgs.get("sentinel") is image

    del MOD.event_ids["nested"]
    MOD.failed_steps.pop()
    MOD.unparsable_files.pop()
    MOD.sprite_imgs.clear()


def test_mod_snapshot_restores_in_place_graphics_metrics(mod_state_isolation):
    catalog = MOD.graphics_catalog
    metrics = catalog.last_metrics
    expected = dict(metrics.__dict__)
    snapshot = _capture_mod_state(MOD)

    metrics.gfx_reads += 1
    del metrics.cache_status
    metrics.__dict__["test_only_metric"] = 1
    catalog.last_metrics = type(metrics)()

    _restore_mod_state(MOD, snapshot)

    assert MOD.graphics_catalog is catalog
    assert catalog.last_metrics is metrics
    assert metrics.__dict__ == expected


def test_shared_fixture_restores_state_before_the_next_test(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    shutil.copyfile(repo / "tests" / "conftest.py", tmp_path / "conftest.py")
    probe = tmp_path / "test_fixture_probe.py"
    probe.write_text(
        textwrap.dedent("""\
            import pytest
            from hoi4cm.mod import MOD

            root = MOD.root
            loaded = MOD.loaded
            failed_steps = tuple(MOD.failed_steps)
            unparsable_files = tuple(MOD.unparsable_files)
            catalog = MOD.graphics_catalog
            metrics = dict(catalog.last_metrics.__dict__)
            images = MOD.sprite_imgs
            image_entries = list(images._data.items())
            maxsize = images.maxsize
            attributes = set(MOD.__dict__)

            @pytest.fixture
            def scenario(mod_state_isolation, monkeypatch):
                MOD.root = "scenario-root"
                MOD.failed_steps.append("scenario failure")
                MOD.unparsable_files.append("scenario.txt")
                MOD.loaded = not loaded
                monkeypatch.setattr(MOD, "loaded", loaded)
                catalog.last_metrics.gfx_reads += 1
                images.maxsize = 1
                images["scenario image"] = object()
                MOD.__dict__["scenario_attribute"] = True

            def test_mutate(scenario):
                assert MOD.root == "scenario-root"
                assert MOD.failed_steps[-1] == "scenario failure"

            def test_observe_restored_state():
                assert MOD.root == root
                assert MOD.loaded == loaded
                assert tuple(MOD.failed_steps) == failed_steps
                assert tuple(MOD.unparsable_files) == unparsable_files
                assert MOD.graphics_catalog is catalog
                assert catalog.last_metrics.__dict__ == metrics
                assert MOD.sprite_imgs is images
                assert list(images._data.items()) == image_entries
                assert images.maxsize == maxsize
                assert set(MOD.__dict__) == attributes
            """),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--no-tk",
            "-q",
            "-c",
            str(repo / "pyproject.toml"),
            str(probe),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "2 passed" in result.stdout, result.stdout
