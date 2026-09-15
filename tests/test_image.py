"""Tests for hoi4cm.core.image — Pillow import gate (opt-in auto-install)."""

import builtins
import os
import re
from pathlib import Path

import pytest

from hoi4cm.core import image


def _force_pil_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("forced missing for test")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_ci_pillow_matches_build_pin():
    if os.environ.get("HOI4CM_REQUIRE_PINNED_PILLOW") != "1":
        pytest.skip("Pillow pin assertion is CI-only")

    try:
        import PIL
    except ImportError:
        pytest.fail("CI requires Pillow, but it is unavailable")

    lock_path = Path(__file__).resolve().parents[1] / "build" / "requirements.txt"
    pillow_lines = [
        line
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("pillow==")
    ]
    assert len(pillow_lines) == 1
    match = re.fullmatch(r"pillow==(\d+\.\d+\.\d+) " + re.escape("\\"), pillow_lines[0])
    assert match is not None
    assert PIL.__version__ == match.group(1)


def test_no_auto_install_without_env(monkeypatch):
    _force_pil_missing(monkeypatch)
    monkeypatch.delenv("HOI4CM_AUTO_INSTALL_PILLOW", raising=False)
    calls = []
    monkeypatch.setattr(
        image, "_try_install_pillow", lambda: calls.append(True) or True
    )

    _img, _tk, ok = image._import_pillow()

    assert ok is False
    assert calls == []  # pip was never invoked


def test_auto_install_attempted_with_env(monkeypatch):
    _force_pil_missing(monkeypatch)
    monkeypatch.setenv("HOI4CM_AUTO_INSTALL_PILLOW", "1")
    calls = []
    monkeypatch.setattr(
        image, "_try_install_pillow", lambda: calls.append(True) or False
    )

    _img, _tk, ok = image._import_pillow()

    assert ok is False
    assert calls == [True]  # opt-in install was attempted
