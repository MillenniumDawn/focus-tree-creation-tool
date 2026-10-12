"""First-launch tutorial step data and preference saving."""

import json
from pathlib import Path

from hoi4cm.ui import tutorial as tutorial_mod


def test_tutorial_has_complete_beginner_workflow():
    assert len(tutorial_mod.TUTORIAL_STEPS) == 8
    assert tutorial_mod.TUTORIAL_STEPS[4].menu_key == "tools"
    assert tutorial_mod.TUTORIAL_STEPS[6].menu_key == "file"
    assert tutorial_mod.TUTORIAL_STEPS[6].menu_item_keys == ("load_mod",)
    assert tutorial_mod.TUTORIAL_STEPS[-1].menu_key == "file"
    assert tutorial_mod.TUTORIAL_STEPS[-1].menu_item_keys == (
        "export_txt",
        "export_mod",
    )


def test_every_tutorial_key_exists_in_each_locale():
    keys = {
        "menu.help",
        "menu.start_tutorial",
        "menu.start_tutorial.tip",
        "tutorial.window.title",
        "tutorial.progress",
        "tutorial.dont_show_again",
        "tutorial.back",
        "tutorial.skip",
        "tutorial.next",
        "tutorial.finish",
    }
    for step in tutorial_mod.TUTORIAL_STEPS:
        keys.update((step.title_key, step.body_key))
    locale_dir = Path(__file__).parents[1] / "locales"
    for path in locale_dir.glob("*.json"):
        strings = json.loads(path.read_text(encoding="utf-8"))
        assert keys <= strings.keys(), f"missing tutorial keys in {path.name}"


def test_save_tutorial_disabled_reports_save_failure(monkeypatch):
    monkeypatch.setattr(tutorial_mod, "cfg_save", lambda values: False)
    assert tutorial_mod.save_tutorial_disabled(True) is False
