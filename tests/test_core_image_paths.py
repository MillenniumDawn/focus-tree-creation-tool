"""Fallback tests for hoi4cm.core.image and hoi4cm.core.paths.

Covers Pillow install/import failure branches and tolerant file-read
fallbacks. Mocks only at the filesystem / Pillow boundary.
"""

from __future__ import annotations

import builtins
import os
import subprocess
import sys

from hoi4cm.core import image, paths

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _force_pil_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("forced missing for test")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)


# ---------------------------------------------------------------------------
# image: _try_install_pillow
# ---------------------------------------------------------------------------


def test_image_pillow_install_failure_returns_false(monkeypatch):
    def _raise(*a, **k):
        raise OSError("no pip")

    monkeypatch.setattr(image.subprocess, "check_call", _raise)
    assert image._try_install_pillow() is False


def test_image_pillow_install_subprocess_failure_returns_false(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.CalledProcessError(1, "pip")

    monkeypatch.setattr(image.subprocess, "check_call", _raise)
    assert image._try_install_pillow() is False


def test_image_pillow_install_runtime_error_returns_false(monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(image.subprocess, "check_call", _raise)
    assert image._try_install_pillow() is False


def test_image_pillow_install_success_returns_true(monkeypatch):
    monkeypatch.setattr(image.subprocess, "check_call", lambda *a, **k: 0)
    assert image._try_install_pillow() is True


# ---------------------------------------------------------------------------
# image: _import_pillow fallback branches
# ---------------------------------------------------------------------------


def test_image_import_failure_after_install(monkeypatch):
    """First import fails, install succeeds, second import still fails."""
    _force_pil_missing(monkeypatch)
    monkeypatch.setenv("HOI4CM_AUTO_INSTALL_PILLOW", "1")
    monkeypatch.setattr(image, "_try_install_pillow", lambda: True)

    real_import = builtins.__import__
    call_count = {"n": 0}

    def fake_import(name, *a, **k):
        if name == "PIL" or name.startswith("PIL."):
            call_count["n"] += 1
            raise ImportError("still missing after install")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    img, tk, ok = image._import_pillow()

    assert ok is False
    assert img is None
    assert tk is None


def test_image_import_oserror_after_install_returns_false(monkeypatch):
    """Second import raises OSError (e.g. broken shared lib) -> False."""
    _force_pil_missing(monkeypatch)
    monkeypatch.setenv("HOI4CM_AUTO_INSTALL_PILLOW", "1")
    monkeypatch.setattr(image, "_try_install_pillow", lambda: True)

    real_import = builtins.__import__
    first = {"done": False}

    def fake_import(name, *a, **k):
        if name == "PIL" or name.startswith("PIL."):
            if not first["done"]:
                first["done"] = True
                raise ImportError("first missing")
            raise OSError("broken Pillow")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    _, _, ok = image._import_pillow()
    assert ok is False


def test_image_frozen_never_installs(monkeypatch):
    _force_pil_missing(monkeypatch)
    monkeypatch.setenv("HOI4CM_AUTO_INSTALL_PILLOW", "1")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    calls: list[bool] = []

    def _track() -> bool:
        calls.append(True)
        return True

    monkeypatch.setattr(image, "_try_install_pillow", _track)

    _, _, ok = image._import_pillow()

    assert ok is False
    assert calls == []


def test_image_auto_install_not_attempted_when_install_fails(monkeypatch):
    _force_pil_missing(monkeypatch)
    monkeypatch.setenv("HOI4CM_AUTO_INSTALL_PILLOW", "1")
    monkeypatch.setattr(image, "_try_install_pillow", lambda: False)

    _, _, ok = image._import_pillow()

    assert ok is False


def test_image_no_auto_install_without_env_does_not_call_install(monkeypatch):
    _force_pil_missing(monkeypatch)
    monkeypatch.delenv("HOI4CM_AUTO_INSTALL_PILLOW", raising=False)
    calls: list[bool] = []

    def _track() -> bool:
        calls.append(True)
        return True

    monkeypatch.setattr(image, "_try_install_pillow", _track)

    _, _, ok = image._import_pillow()

    assert ok is False
    assert calls == []


# ---------------------------------------------------------------------------
# paths: read_file fallbacks
# ---------------------------------------------------------------------------


def test_paths_read_file_mixed_encoding_returns_none(monkeypatch, tmp_path):
    p = tmp_path / "mixed.txt"
    p.write_bytes(b"\xff\xfe\xfd")

    def fake_open(path, *a, **k):
        raise OSError("unreadable")

    monkeypatch.setattr(builtins, "open", fake_open)
    # getsize should not short-circuit; return small size
    monkeypatch.setattr(os.path, "getsize", lambda _: 3)

    assert paths.read_file(str(p)) is None


def test_paths_read_file_value_error_returns_none(monkeypatch, tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("hello", encoding="utf-8")

    def fake_open(path, *a, **k):
        raise ValueError("bad encoding arg")

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(os.path, "getsize", lambda _: 5)

    assert paths.read_file(str(p)) is None


def test_paths_read_file_unicode_decode_error_returns_none(monkeypatch, tmp_path):
    p = tmp_path / "ud.txt"
    p.write_text("hello", encoding="utf-8")

    def fake_open(path, *a, **k):
        raise UnicodeDecodeError("utf-8", b"", 0, 1, "test")

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(os.path, "getsize", lambda _: 5)

    assert paths.read_file(str(p)) is None


def test_paths_read_file_streaming_oversize_returns_none(tmp_path):
    p = tmp_path / "stream.txt"
    p.write_text("x" * 20, encoding="utf-8")
    # max_bytes=10 but file is 20 bytes; read(max_bytes+1) will be 11 -> oversize
    assert paths.read_file(str(p), max_bytes=10) is None


def test_paths_read_file_getsize_oserror_still_reads(tmp_path, monkeypatch):
    p = tmp_path / "ok.txt"
    p.write_text("hello", encoding="utf-8")

    def _raise(_path: str):
        raise OSError("no stat")

    monkeypatch.setattr(os.path, "getsize", _raise)

    assert paths.read_file(str(p)) == "hello"


def test_paths_read_file_oversize_via_getsize_returns_none(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 100, encoding="utf-8")
    assert paths.read_file(str(p), max_bytes=10) is None


def test_paths_read_file_latin1_fallback(tmp_path, monkeypatch):
    p = tmp_path / "latin.txt"
    # bytes valid as latin-1 but we force utf-8 opens to fail to test fallback loop
    p.write_bytes("café".encode("latin-1"))

    real_open = builtins.open

    def fake_open(path, *a, **k):
        enc = k.get("encoding", "")
        if enc in ("utf-8-sig", "utf-8"):
            raise ValueError(f"forced fail for {enc}")
        return real_open(path, *a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)
    # Don't mock getsize; let real size pass the cap
    assert paths.read_file(str(p)) == "café"


def test_paths_read_file_max_bytes_none_reads_large(tmp_path):
    p = tmp_path / "large.txt"
    p.write_text("y" * 5000, encoding="utf-8")
    assert paths.read_file(str(p), max_bytes=None) == "y" * 5000


def test_paths_read_file_missing_returns_empty(tmp_path):
    assert paths.read_file(str(tmp_path / "nope.txt")) == ""


def test_paths_autosave_makedirs_failure_still_returns_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))

    def fake_makedirs(*a, **k):
        raise OSError("read-only")

    monkeypatch.setattr(os, "makedirs", fake_makedirs)

    got = paths.autosave_path("test.json")
    assert got.endswith(os.path.join(".hoi4cm", "autosave", "test.json"))
