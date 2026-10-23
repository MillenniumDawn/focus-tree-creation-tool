"""Undo labels stay English on the stack and are translated for display."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from hoi4cm.core import i18n as i18n_mod
from hoi4cm.ui.undo_labels import UNDO_LABEL_KEYS, undo_label_text

ROOT = Path(__file__).parents[1]
SOURCE_PATHS = [
    *sorted((ROOT / "src" / "hoi4cm").rglob("*.py")),
    ROOT / "hoi4_content_maker.py",
]
# Argument position of the label for each call that puts one on the stack.
_LABEL_ARG = {"_push_undo": 0, "record": 0, "track": 1}


def _literals(node: ast.expr) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _literals(node.body) | _literals(node.orelse)
    return set()


def _pushed_labels() -> set[str]:
    labels: set[str] = set()
    for path in SOURCE_PATHS:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            position = _LABEL_ARG.get(name)
            if position is not None and len(node.args) > position:
                labels |= _literals(node.args[position])
    return labels


def test_every_pushed_label_has_a_translation_key():
    assert sorted(_pushed_labels() - set(UNDO_LABEL_KEYS)) == []


def test_label_table_has_no_stale_entries():
    # "action" is the default label of _push_undo, not a literal at a call site.
    assert sorted(set(UNDO_LABEL_KEYS) - _pushed_labels() - {"action"}) == []


def test_english_text_is_the_label_itself():
    english = json.loads((ROOT / "locales" / "en.json").read_text(encoding="utf-8"))

    wrong = {
        label: english.get(key)
        for label, key in UNDO_LABEL_KEYS.items()
        if english.get(key) != label
    }

    assert wrong == {}


def test_label_text_follows_the_ui_language(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        i18n_mod, "I18N_STRINGS", {"undo.add_focus": "Fokus hinzufügen"}
    )

    assert undo_label_text("add focus") == "Fokus hinzufügen"
    assert undo_label_text("move focus") == "move focus"


def test_unknown_label_is_shown_unchanged():
    assert undo_label_text("something new") == "something new"
