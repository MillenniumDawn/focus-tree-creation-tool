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


def test_read_file_falls_back_to_latin1(tmp_path):
    p = tmp_path / "c.txt"
    p.write_bytes("café".encode("latin-1"))  # 0xe9 is not valid UTF-8
    assert paths.read_file(str(p)) == "café"
    assert "�" not in paths.read_file(str(p))


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


def test_read_file_respects_size_cap(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 5000, encoding="utf-8")
    assert paths.read_file(str(p), max_bytes=1000) == ""


def test_read_file_reads_within_cap(tmp_path):
    p = tmp_path / "small.txt"
    p.write_text("focus = {", encoding="utf-8")
    assert paths.read_file(str(p), max_bytes=1000) == "focus = {"


def test_read_file_cap_disabled(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 5000, encoding="utf-8")
    assert paths.read_file(str(p), max_bytes=None) == "x" * 5000


def test_autosave_path_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    got = paths.autosave_path("decision.json")
    assert got == os.path.join(str(tmp_path), ".hoi4cm", "autosave", "decision.json")
    assert os.path.isdir(os.path.dirname(got))
