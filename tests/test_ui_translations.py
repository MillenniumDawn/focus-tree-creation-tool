"""The editor, explorer and Spotlight text follows the active UI language."""

from types import SimpleNamespace

import pytest

from hoi4cm.core import i18n as i18n_mod
from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.editor_chrome import EditorStatus
from hoi4cm.ui.focus_actions import action_labels
from hoi4cm.ui.project_index import project_items


@pytest.fixture
def english():
    saved = (i18n_mod.I18N_LANG, dict(i18n_mod.I18N_STRINGS))
    i18n_mod._load_i18n("en")
    yield
    i18n_mod.I18N_LANG, i18n_mod.I18N_STRINGS = saved


def explorer_labels():
    app = SimpleNamespace(
        _last_project_path="",
        _navigation_started=True,
        _navigation_source="",
        workspace=SimpleNamespace(main_tree=SimpleNamespace(file_path="")),
        focuses=FocusDocument(),
        _extra_trees=[],
        _tree_id=SimpleNamespace(get=lambda: ""),
    )
    mod = SimpleNamespace(root="", mod_name="")
    return [item.label for item in project_items(app, mod)]


def snapshot():
    return [
        *action_labels().values(),
        *EditorStatus().labels(None),
        *explorer_labels(),
    ]


@pytest.mark.parametrize("language", ["de", "es", "zh_CN"])
def test_new_ui_text_is_translated(english, language):
    baseline = snapshot()
    i18n_mod._load_i18n(language)
    translated = snapshot()
    assert len(translated) == len(baseline)
    untranslated = [
        english_text
        for english_text, text in zip(baseline, translated, strict=True)
        if text == english_text
    ]
    assert untranslated == []
