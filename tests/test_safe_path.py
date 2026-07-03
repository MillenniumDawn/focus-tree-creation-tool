"""Tests for hoi4cm.core.safe_path — filename component sanitization."""

import os

import pytest

from hoi4cm.core import safe_path


@pytest.mark.parametrize(
    "raw",
    [
        "../../etc/passwd",
        "a/b/c",
        "/etc/passwd",
        "..\\..\\windows\\system32",
        "foo\nbar",
        "foo\x00bar",
    ],
)
def test_sanitize_strips_traversal_to_single_segment(raw):
    out = safe_path.sanitize_component(raw)
    assert os.sep not in out
    assert "/" not in out and "\\" not in out
    assert ".." not in out.split(os.sep)
    assert "\n" not in out and "\x00" not in out


@pytest.mark.parametrize(
    "raw",
    ["GER", "TAG_my_spirit", "focus_1", "MD_money", "namespace-1", "a.b"],
)
def test_sanitize_passes_valid_ids_unchanged(raw):
    assert safe_path.sanitize_component(raw) == raw


@pytest.mark.parametrize("raw", ["", ".", "..", "   ", "/", "///"])
def test_sanitize_rejects_empty_and_dot_names(raw):
    assert safe_path.sanitize_component(raw) == "unnamed"


def test_sanitize_custom_fallback():
    assert safe_path.sanitize_component("..", fallback="x") == "x"


def test_safe_join_accepts_in_tree(tmp_path):
    got = safe_path.safe_join(str(tmp_path), "common", "ideas", "GER.txt")
    assert got == os.path.realpath(
        os.path.join(str(tmp_path), "common", "ideas", "GER.txt")
    )


def test_safe_join_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        safe_path.safe_join(str(tmp_path), "..", "..", "escape.txt")


def test_safe_join_rejects_absolute_component(tmp_path):
    with pytest.raises(ValueError):
        safe_path.safe_join(str(tmp_path), "/etc/passwd")
