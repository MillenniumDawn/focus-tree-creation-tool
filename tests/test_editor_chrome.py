"""Headless tests for editor state, navigation, and selected-form tracking."""

from types import SimpleNamespace
from unittest.mock import Mock

from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.editor_chrome import (
    EditorChrome,
    EditorStatus,
    editor_is_dirty,
    mark_editor_changed,
    mark_editor_saved,
    observe_selected_content,
    pending_editor_changes,
    validation_completed,
    validation_signature,
)


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


def app_state():
    return SimpleNamespace(
        focuses=FocusDocument(),
        _tree_id=Value("test_tree"),
        _cfp_x_var=Value(),
        _cfp_y_var=Value(),
        _extra_trees=[],
        selected=None,
    )


def test_save_and_validation_have_independent_boundaries():
    app = app_state()
    mark_editor_saved(app)
    initial = validation_signature(app)
    assert app._editor_status.labels(initial) == ("Saved", "Validation: not run")
    validation_completed(app, initial)
    mark_editor_changed(app)
    changed = validation_signature(app)
    assert app._editor_status.labels(changed) == ("Unsaved", "Validation: outdated")
    mark_editor_saved(app)
    assert app._editor_status.labels(changed) == ("Saved", "Validation: outdated")
    validation_completed(app, changed)
    assert app._editor_status.labels(changed) == ("Saved", "Validation: current")


def test_late_validation_result_does_not_validate_newer_geometry():
    app = app_state()
    old = validation_signature(app)
    app.focuses.new_focus(1, 2)
    app.focuses.touch()
    validation_completed(app, old)
    assert (
        app._editor_status.labels(validation_signature(app))[1]
        == "Validation: outdated"
    )


def test_signature_snapshots_metadata_and_ignores_membership_iteration():
    class UnreadableIds:
        def __iter__(self):
            raise AssertionError("status must not walk focus IDs")

    app = app_state()
    app._extra_trees = [{"focus_ids": UnreadableIds(), "tree_id": "shared"}]
    app._shared_focuses = ["shared"]
    initial = validation_signature(app)
    app._shared_focuses.append("another")
    assert validation_signature(app) != initial
    initial = validation_signature(app)
    app._cfp_x_var.value = "12"
    assert validation_signature(app) != initial


def test_pending_form_invalidates_saved_and_validated_status():
    state = EditorStatus(saved=(1,), validated=(1,))
    assert state.labels((1,), pending=True) == ("Unsaved", "Validation: outdated")
    app = app_state()
    app.selected = object()
    app._fv_name = Value()
    app._fv_ai_raw = SimpleNamespace(get=lambda *_: "base = 1")
    app._fv_icon = Value()
    app._fv_gfx = Value()
    app._fv_cost = Value("invalid")
    assert pending_editor_changes(app)
    app.selected = None
    assert not pending_editor_changes(app)


def test_status_poll_reschedules_and_reports_a_failing_refresh_once(monkeypatch):
    errors = []
    monkeypatch.setattr("hoi4cm.ui.editor_chrome.add_error", errors.append)
    app = SimpleNamespace(after=Mock(return_value="job"), after_cancel=Mock())
    chrome = EditorChrome(app)
    chrome.refresh = Mock(side_effect=RuntimeError("boom"))

    chrome.start()
    chrome.start()

    assert app.after.call_count == 2, "a failed refresh must still reschedule"
    assert len(errors) == 1 and "boom" in errors[0]

    chrome.refresh = Mock()
    chrome.start()
    chrome.refresh = Mock(side_effect=RuntimeError("again"))
    chrome.start()
    assert len(errors) == 2, "a new failure after recovery is reported again"


def test_closed_status_poll_stops_rescheduling():
    app = SimpleNamespace(after=Mock(return_value="job"), after_cancel=Mock())
    chrome = EditorChrome(app)
    chrome.refresh = Mock()
    chrome.start()
    chrome.close()
    app.after_cancel.assert_called_once_with("job")
    chrome.start()
    assert app.after.call_count == 1


def test_reveal_and_action_menu_use_selected_focus_id():
    calls = []
    app = app_state()
    app._center_on_focus = lambda focus_id: calls.append(("reveal", focus_id))
    app._focus_actions = SimpleNamespace(
        show=lambda focus_id: calls.append(("actions", focus_id))
    )
    chrome = EditorChrome(app)
    chrome.reveal()
    chrome.actions()
    assert calls == []
    app.selected = SimpleNamespace(id=42)
    chrome.reveal()
    chrome.actions()
    assert calls == [("reveal", 42), ("actions", 42)]


def selected_form(app):
    focus = app.focuses.new_focus(0, 0)
    app.selected = focus
    for field, value in {
        "name": focus.name,
        "icon": focus.icon,
        "gfx": focus.gfx,
        "cost": "10",
        "x": "0",
        "y": "0",
        "loc_name": "",
        "search": "FOCUS_FILTER_POLITICAL",
        "cancel": focus.cancel_if_invalid,
        "continue": focus.continue_if_invalid,
        "cap": focus.available_if_capitulated,
    }.items():
        setattr(app, f"_fv_{field}", Value(value))
    for field in ("desc", "avail", "bypass", "cancel2", "ai_raw"):
        value = "base = 1" if field == "ai_raw" else ""
        setattr(app, f"_fv_{field}", SimpleNamespace(get=lambda *_, value=value: value))
    app._read_offsets_from_form = lambda: []
    app._code_edit_mode = [False]
    return focus


def test_selected_form_and_code_edits_are_detected_without_mutating_document():
    app = app_state()
    focus = selected_form(app)
    revision = app.focuses.revision
    assert not pending_editor_changes(app)
    app._fv_loc_name.value = "Changed title"
    assert pending_editor_changes(app)
    app._fv_loc_name.value = ""
    assert not pending_editor_changes(app)
    app._code_edit_mode[0] = True
    app._build_focus_code = lambda _: "focus = { }"
    app._code_txt = SimpleNamespace(get=lambda *_: "focus = { }\n")
    assert not pending_editor_changes(app)
    app._code_txt.get = lambda *_: "invalid draft"
    assert pending_editor_changes(app)
    assert app.focuses.revision == revision
    assert focus.loc_name == ""


def test_focus_navigation_preserves_open_wizard_draft():
    calls = []
    app = app_state()
    app.lift = lambda: calls.append("lift")
    app.cv = SimpleNamespace(focus_set=lambda: calls.append("canvas"))
    for attr in ("_editor_context_lbl", "_editor_zoom_lbl"):
        setattr(app, attr, SimpleNamespace(config=lambda **_: None))
    app.zoom = 1.0
    chrome = EditorChrome(app)
    chrome.windows["Events"] = SimpleNamespace(
        lower=lambda _: calls.append("lower"), grab_release=lambda: None
    )
    chrome.active_content = "Events"
    chrome.navigate("Focus Trees")
    assert calls == ["lower", "lift", "canvas"]
    assert "Events" in chrome.windows
    assert chrome.active_content == "Focus Trees"


def test_observed_committed_fields_and_nested_effects_invalidate_status():
    app = app_state()
    focus = app.focuses.new_focus(0, 0)
    app.selected = focus
    mark_editor_saved(app)
    validation_completed(app, validation_signature(app))
    focus.loc_name = "Committed title"
    signature = validation_signature(app)
    assert app._editor_status.labels(signature) == ("Unsaved", "Validation: outdated")
    mark_editor_saved(app)
    focus.effects.append({"type": "add_stability", "value": "0.1"})
    assert app._editor_status.labels(validation_signature(app))[0] == "Unsaved"
    mark_editor_saved(app)
    focus.effects[0]["value"] = "0.2"
    assert app._editor_status.labels(validation_signature(app))[0] == "Unsaved"
    mark_editor_saved(app)
    assert app._editor_status.labels(validation_signature(app))[0] == "Saved"


def test_selecting_an_unchanged_focus_does_not_dirty_editor():
    app = app_state()
    first = app.focuses.new_focus(0, 0)
    second = app.focuses.new_focus(1, 0)
    app.selected = first
    mark_editor_saved(app)
    initial = validation_signature(app)
    app.selected = second
    assert validation_signature(app) == initial
    app.selected = None
    assert validation_signature(app) == initial
    app.selected = first
    assert validation_signature(app) == initial


def test_committed_observation_clears_only_changed_autosave_writer():
    app = app_state()
    focus = app.focuses.new_focus(0, 0)
    app.selected = focus
    writer = app._autosave_writer = object()
    observe_selected_content(app)
    assert app._autosave_writer is writer
    observe_selected_content(app)
    assert app._autosave_writer is writer
    focus.cost = 15
    observe_selected_content(app)
    assert app._autosave_writer is None
    replacement = app._autosave_writer = object()
    observe_selected_content(app)
    assert app._autosave_writer is replacement
    focus.effects.append({"type": "add_stability", "value": "0.1"})
    observe_selected_content(app)
    assert app._autosave_writer is None


def test_editor_dirty_tracks_pending_committed_and_saved_form():
    app = app_state()
    focus = selected_form(app)
    mark_editor_saved(app)
    assert not editor_is_dirty(app)
    app._fv_cost.value = "15"
    assert editor_is_dirty(app)
    app._fv_cost.value = "10"
    assert not editor_is_dirty(app)
    focus.cost = 15
    app._fv_cost.value = "15"
    assert editor_is_dirty(app)
    mark_editor_saved(app)
    assert not editor_is_dirty(app)
    app._fv_cost.value = "invalid"
    assert editor_is_dirty(app)
