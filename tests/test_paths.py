"""Tests for hoi4cm.core.paths — mod-dir defaults and tolerant file reading."""

import os
import sys

from hoi4cm.core import paths


def test_read_file_utf8(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("héllo wörld", encoding="utf-8")
    assert paths.read_file(str(p)) == "héllo wörld"


def test_read_file_strips_utf8_bom(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes("focus = {".encode("utf-8-sig"))  # leading BOM
    assert paths.read_file(str(p)) == "focus = {"


def test_read_file_missing_returns_empty(tmp_path):
    assert paths.read_file(str(tmp_path / "does_not_exist.txt")) == ""


def test_default_mod_dir_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    expected = os.path.join(
        ".local", "share", "Paradox Interactive", "Hearts of Iron IV", "mod"
    )
    assert paths.default_hoi4_mod_dir().endswith(expected)


def test_default_mod_dir_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    d = paths.default_hoi4_mod_dir()
    assert os.path.join("Library", "Application Support") in d
    assert d.endswith(os.path.join("Hearts of Iron IV", "mod"))


def test_default_mod_dir_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    d = paths.default_hoi4_mod_dir()
    assert d.endswith(
        os.path.join("Documents", "Paradox Interactive", "Hearts of Iron IV", "mod")
    )
