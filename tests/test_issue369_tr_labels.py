"""Regression tests for issue #369 (translation routing)."""

from __future__ import annotations

import ast
from pathlib import Path

from test_i18n_keys import _tr_calls

ROOT = Path(__file__).parents[1]
DECISION_PATH = ROOT / "src" / "hoi4cm" / "wizards" / "decision.py"
SETTINGS_PATH = ROOT / "src" / "hoi4cm" / "ui" / "settings_dialog.py"


def _calls_with_key(path: Path, key: str) -> list[ast.Call]:
    return [
        call
        for call in _tr_calls(path)
        if isinstance(call.args[0], ast.Constant) and call.args[0].value == key
    ]


def _literal_default(call: ast.Call) -> str | None:
    arg = call.args[1]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _is_tr_call(expr: ast.expr, key: str) -> bool:
    return (
        isinstance(expr, ast.Call)
        and bool(expr.args)
        and isinstance(expr.func, ast.Name)
        and expr.func.id == "tr"
        and isinstance(expr.args[0], ast.Constant)
        and expr.args[0].value == key
    )


def test_decision_preview_tab_uses_its_own_colonless_key():
    [call] = _calls_with_key(DECISION_PATH, "decision.tab.preview")

    assert _literal_default(call) == "Preview"


def test_decision_colon_label_keeps_the_existing_colon_key():
    [call] = _calls_with_key(DECISION_PATH, "common.preview")

    assert _literal_default(call) == "Preview:"


def test_settings_md_overridden_state_branches_are_tr_calls():
    [call] = _calls_with_key(SETTINGS_PATH, "settings.md_overridden")
    state = next(kw for kw in call.keywords if kw.arg == "state").value

    assert isinstance(state, ast.IfExp)
    assert _is_tr_call(state.body, "settings.md_state_on")
    assert _is_tr_call(state.orelse, "settings.md_state_off")


def test_settings_active_badge_is_translated():
    badge_ifexp = next(
        node
        for node in ast.walk(ast.parse(SETTINGS_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.IfExp)
        and _is_tr_call(node.body, "settings.event_profile.active")
        and isinstance(node.orelse, ast.Constant)
        and node.orelse.value == ""
    )

    assert badge_ifexp is not None


def test_settings_active_badge_label_has_no_fixed_width():
    label = next(
        node
        for node in ast.walk(ast.parse(SETTINGS_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "Label"
        and any(
            isinstance(kw.value, ast.Name) and kw.value.id == "badge"
            for kw in node.keywords
            if kw.arg == "text"
        )
    )

    assert not any(kw.arg == "width" for kw in label.keywords)
