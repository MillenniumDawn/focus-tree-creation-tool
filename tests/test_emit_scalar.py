import pytest

from hoi4cm.script.syntax import emit_scalar


def test_emit_scalar_empty():
    assert emit_scalar("") == ""


def test_emit_scalar_no_special_chars():
    assert emit_scalar("hello") == "hello"
    assert (
        emit_scalar("GFX_goal_generic_political_pressure")
        == "GFX_goal_generic_political_pressure"
    )
    assert emit_scalar("TST_a") == "TST_a"
    assert emit_scalar("VEN") == "VEN"
    assert emit_scalar("1") == "1"
    assert emit_scalar("yes") == "yes"


def test_emit_scalar_quotes_on_whitespace():
    assert emit_scalar("hello world") == '"hello world"'
    assert emit_scalar("hello\tworld") == '"hello\tworld"'
    assert emit_scalar("hello\nworld") == '"hello\nworld"'
    assert emit_scalar("hello\rworld") == '"hello\rworld"'


def test_emit_scalar_quotes_on_braces_equals_hash():
    assert emit_scalar("hello{world") == '"hello{world"'
    assert emit_scalar("hello}world") == '"hello}world"'
    assert emit_scalar("hello=world") == '"hello=world"'
    assert emit_scalar("hello#world") == '"hello#world"'


def test_emit_scalar_rejects_embedded_quote():
    with pytest.raises(ValueError, match=r'hello"world'):
        emit_scalar('hello"world')


def test_emit_scalar_icon_path_with_space():
    assert emit_scalar("gfx/with a space/goal.dds") == '"gfx/with a space/goal.dds"'


def test_emit_scalar_multiword_text():
    assert emit_scalar("Multi word title") == '"Multi word title"'
