"""Key drift guard for the UI translations (issue #21).

``tr(key, default)`` falls back to the inline English default, so a key that is
missing from ``locales/en.json``, or a default that differs from it, changes
the text when the locale fails to load. These tests read the ``tr()`` calls
out of the source and compare them with the locale files.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from collections.abc import Iterator
from functools import cache
from pathlib import Path

import pytest
from source_scan import ROOT, SOURCE_PATHS, source_calls

from hoi4cm.ui import tutorial as tutorial_mod
from hoi4cm.ui.undo_labels import UNDO_LABEL_KEYS

ENGLISH_PATH = ROOT / "locales" / "en.json"
LOCALE_PATHS = sorted((ROOT / "locales").glob("*.json"))
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

_PICKERS = ("effect", "trigger")
_SHARED = "src/hoi4cm/wizards/_shared.py"
_TUTORIAL = "src/hoi4cm/ui/tutorial.py"

# tr() calls whose key is not a string literal. The scan cannot see the keys
# they build, so each call site is listed here with every key it can produce.
# A new dynamic call site, or a changed one, fails until it is listed.
DYNAMIC_KEYS: dict[tuple[str, str], set[str]] = {
    (_SHARED, "f'{picker_key}_picker.title'"): {
        f"{picker}_picker.title" for picker in _PICKERS
    },
    (_SHARED, "search_key"): {
        "focus.effects.search_placeholder",
        "trigger_picker.search_placeholder",
    },
    (_SHARED, "none_key"): {
        "focus.effects.none_found",
        "trigger_picker.none_found",
    },
    (_SHARED, "f'{picker_key}_picker.preview'"): {
        f"{picker}_picker.preview" for picker in _PICKERS
    },
    (
        _SHARED,
        "'effect_picker.insert_effect' if picker_key == 'effect' "
        "else f'{picker_key}_picker.insert_item'",
    ): {"effect_picker.insert_effect", "trigger_picker.insert_item"},
    (
        _SHARED,
        "'effect_picker.insert_hint' if picker_key == 'effect' "
        "else f'{picker_key}_picker.insert_hint'",
    ): {"effect_picker.insert_hint", "trigger_picker.insert_hint"},
    (_TUTORIAL, "step.title_key"): {s.title_key for s in tutorial_mod.TUTORIAL_STEPS},
    (_TUTORIAL, "step.body_key"): {s.body_key for s in tutorial_mod.TUTORIAL_STEPS},
    ("src/hoi4cm/ui/undo_labels.py", "key"): set(UNDO_LABEL_KEYS.values()),
}


def _strings(path: Path) -> dict[str, str]:
    """A locale file's translations, without its ``_meta`` block."""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return {k: v for k, v in data.items() if k != "_meta"}


def _tr_calls(path: Path) -> Iterator[ast.Call]:
    for node in source_calls(path):
        if not node.args:
            continue
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "tr") or (
            isinstance(func, ast.Attribute) and func.attr == "tr"
        ):
            yield node


def _literal_keys(arg: ast.expr) -> list[str] | None:
    """Keys named by a literal, or by a conditional between two literals."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return [arg.value]
    if isinstance(arg, ast.IfExp):
        body, orelse = _literal_keys(arg.body), _literal_keys(arg.orelse)
        if body is not None and orelse is not None:
            return body + orelse
    return None


@cache
def _scan() -> tuple[dict[str, list[str]], set[tuple[str, str]]]:
    """Return ``({literal key: [path:line, ...]}, {(path, key expression)})``."""
    literal: dict[str, list[str]] = {}
    dynamic: set[tuple[str, str]] = set()
    for path in SOURCE_PATHS:
        rel = path.relative_to(ROOT).as_posix()
        for call in _tr_calls(path):
            keys = _literal_keys(call.args[0])
            if keys is None:
                dynamic.add((rel, ast.unparse(call.args[0])))
                continue
            for key in keys:
                literal.setdefault(key, []).append(f"{rel}:{call.lineno}")
    return literal, dynamic


def _dynamic_keys() -> set[str]:
    return set().union(*DYNAMIC_KEYS.values())


def test_scan_reads_the_monolith_and_the_package():
    literal, _dynamic = _scan()

    assert any(
        site.startswith("hoi4_content_maker.py") for site in literal["status.tree"]
    )
    assert any(site.startswith("src/hoi4cm/") for site in literal["common.cancel"])


def test_tr_calls_do_not_use_its_own_parameter_names_as_placeholders():
    """A ``key=`` or ``default=`` placeholder collides with ``tr``'s parameters
    and raises TypeError when the call runs."""
    clashes = [
        f"{path.relative_to(ROOT).as_posix()}:{call.lineno}"
        for path in SOURCE_PATHS
        for call in _tr_calls(path)
        if any(kw.arg in ("key", "default") for kw in call.keywords)
    ]

    assert clashes == []


def test_tr_calls_supply_every_placeholder_of_the_english_text():
    """A placeholder with no matching keyword is shown raw, with no error."""
    english = _strings(ENGLISH_PATH)
    unsupplied = []
    for path in SOURCE_PATHS:
        for call in _tr_calls(path):
            keys = _literal_keys(call.args[0])
            if keys is None or any(kw.arg is None for kw in call.keywords):
                continue
            supplied = {kw.arg for kw in call.keywords}
            for key in keys:
                needed = set(_PLACEHOLDER_RE.findall(english.get(key, ""))) - supplied
                if needed:
                    where = f"{path.relative_to(ROOT).as_posix()}:{call.lineno}"
                    unsupplied.append(f"{where} {key} needs {sorted(needed)}")

    assert unsupplied == []


def test_every_literal_tr_key_is_in_the_english_locale():
    english = _strings(ENGLISH_PATH)
    literal, _dynamic = _scan()

    missing = sorted(
        f"{key} ({sites[0]})" for key, sites in literal.items() if key not in english
    )

    assert missing == []


def test_literal_tr_defaults_match_english_locale():
    """A string-literal default must equal the English value for its key."""
    english = _strings(ENGLISH_PATH)
    mismatches = []
    for path in SOURCE_PATHS:
        rel = path.relative_to(ROOT).as_posix()
        for call in _tr_calls(path):
            if len(call.args) < 2:
                continue
            keys = _literal_keys(call.args[0])
            default = call.args[1]
            if (
                keys is None
                or not isinstance(default, ast.Constant)
                or not isinstance(default.value, str)
            ):
                continue
            for key in keys:
                expected = english.get(key)
                if expected != default.value:
                    mismatches.append(
                        f"{rel}:{call.lineno} {key}: "
                        f"{default.value!r} != {expected!r}"
                    )

    assert mismatches == []


def _is_literal_file_filter(node: ast.AST) -> bool:
    """A ``("label", "*.ext")`` pair whose label is a bare string."""
    if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
        return False
    label, pattern = node.elts
    return (
        isinstance(label, ast.Constant)
        and isinstance(label.value, str)
        and isinstance(pattern, ast.Constant)
        and isinstance(pattern.value, str)
        and pattern.value.startswith("*")
    )


def test_file_dialog_filter_labels_go_through_tr():
    """Tk shows a file-type filter's label, so it must be translated."""
    untranslated = [
        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
        for path in SOURCE_PATHS
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if _is_literal_file_filter(node)
    ]

    assert untranslated == []


def test_dynamic_tr_calls_are_all_declared():
    _literal, dynamic = _scan()

    assert dynamic == set(DYNAMIC_KEYS)


def test_every_declared_dynamic_key_is_in_the_english_locale():
    english = _strings(ENGLISH_PATH)

    assert sorted(_dynamic_keys() - set(english)) == []


def test_english_locale_has_no_orphaned_keys():
    english = _strings(ENGLISH_PATH)
    literal, _dynamic = _scan()

    assert sorted(set(english) - set(literal) - _dynamic_keys()) == []


@pytest.mark.parametrize("path", LOCALE_PATHS, ids=lambda path: path.stem)
def test_locale_has_exactly_the_english_keys(path: Path):
    english = set(_strings(ENGLISH_PATH))
    keys = set(_strings(path))

    assert (sorted(english - keys), sorted(keys - english)) == ([], [])


@pytest.mark.parametrize("path", LOCALE_PATHS, ids=lambda path: path.stem)
def test_locale_names_itself_in_meta(path: Path):
    meta = json.loads(path.read_text(encoding="utf-8"))["_meta"]

    assert isinstance(meta, dict)
    assert isinstance(meta["display_name"], str)
    assert meta["display_name"].strip()


@pytest.mark.parametrize("path", LOCALE_PATHS, ids=lambda path: path.stem)
def test_locale_preserves_named_placeholders(path: Path):
    english = _strings(ENGLISH_PATH)
    translated = _strings(path)

    mismatched = [
        key
        for key, text in english.items()
        if Counter(_PLACEHOLDER_RE.findall(translated.get(key, "")))
        != Counter(_PLACEHOLDER_RE.findall(text))
    ]

    assert mismatched == []
