"""Headless coverage for the decision wizard's save-confirmation rule."""

import hoi4cm.wizards.decision as decision_mod


def test_decision_save_confirmation_detects_other_existing_target(tmp_path):
    source = tmp_path / "imported.txt"
    target = tmp_path / "other.txt"

    assert not decision_mod.decision_save_needs_confirmation(
        str(source), str(source), True
    )
    assert decision_mod.decision_save_needs_confirmation(str(target), str(source), True)
    assert not decision_mod.decision_save_needs_confirmation(
        str(target), str(source), False
    )
