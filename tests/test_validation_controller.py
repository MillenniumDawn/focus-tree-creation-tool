"""Validation input keys, bounded dispatch, and current-result adoption."""

from typing import cast
from unittest.mock import Mock

import pytest

import hoi4_content_maker as app_module
from hoi4cm.core.app_config import AppConfig
from hoi4cm.mod.index import ModIndex
from hoi4cm.models import Focus, FocusDocument
from hoi4cm.ui import validation as validation_ui
from hoi4cm.ui.canvas_scheduler import RedrawChannel
from hoi4cm.ui.lifecycle import ApplicationLifecycle


class _Host:
    def __init__(self):
        self.focuses = FocusDocument([Focus(id=1, x=0, y=0)])
        self.index = ModIndex()
        self.app_config = AppConfig()
        self.edit_loc_file = ""
        self._lifecycle = ApplicationLifecycle(None)
        self.jobs = {}
        self._next_job = 0
        self._validation_issues = []
        self._validation_worst = {}
        self._validation_win = None
        self._redraw = Mock()
        self._invalidate_focus_list_structure = Mock()
        self.applied = []
        self.controller = validation_ui.ValidationController(self)

    def after(self, delay, callback):
        self._next_job += 1
        self.jobs[self._next_job] = (delay, callback)
        return self._next_job

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def fire(self, delay=150):
        job = next(job for job, (ms, _) in self.jobs.items() if ms == delay)
        _, callback = self.jobs.pop(job)
        callback()

    def _validation_sprites(self):
        return app_module.App._validation_sprites(cast(app_module.App, self))

    def _apply_validation_result(self, issues):
        self.applied.append(issues)
        app_module.App._apply_validation_result(cast(app_module.App, self), issues)


@pytest.fixture
def dispatch(monkeypatch):
    host = _Host()
    tasks = []
    captures = Mock(wraps=validation_ui.capture_validation_snapshot)
    loc_reads = Mock(wraps=validation_ui.collect_loc_keys_from_file)
    validations = Mock(wraps=validation_ui.validate_document)
    monkeypatch.setattr(validation_ui, "capture_validation_snapshot", captures)
    monkeypatch.setattr(validation_ui, "collect_loc_keys_from_file", loc_reads)
    monkeypatch.setattr(validation_ui, "validate_document", validations)

    def submit(_owner, work, on_done, *, on_error, **_kwargs):
        tasks.append((work, on_done, on_error))

    monkeypatch.setattr(validation_ui, "run_bg", submit)
    yield host, tasks, captures, loc_reads, validations
    host._lifecycle.close()


def _finish(tasks):
    work, done, _ = tasks.pop(0)
    done(work())


def test_unchanged_requests_and_result_redraw_do_not_repeat_work(dispatch):
    host, tasks, captures, loc_reads, validations = dispatch
    host.controller.schedule()
    host.fire()
    _finish(tasks)
    for _ in range(20):
        host.controller.schedule()
    assert host.jobs == {}
    assert captures.call_count == loc_reads.call_count == validations.call_count == 1
    assert len(host.applied) == 1
    host._redraw.assert_called_once_with(channels=RedrawChannel.VIEW)


@pytest.mark.parametrize(
    "change",
    [
        "content",
        "geometry",
        "document",
        "catalog_generation",
        "catalog",
        "loaded",
        "loc_target",
        "loc_language",
        "ui_language",
    ],
)
def test_relevant_inputs_refresh_even_without_geometry_changes(
    dispatch, monkeypatch, change
):
    host, tasks, captures, _, _ = dispatch
    host.controller.run()
    _finish(tasks)
    doc = host.focuses
    geometry_revision = doc.geometry_revision
    if change == "content":
        doc[1].desc = "new description"
        doc.mark_content_changed()
        assert doc.geometry_revision == geometry_revision
    elif change == "geometry":
        doc.move(1, 4, 5)
    elif change == "document":
        host.focuses = FocusDocument([Focus(id=1, x=0, y=0)])
        assert host.focuses.content_revision == doc.content_revision
    elif change == "catalog_generation":
        host.index.graphics_catalog.generation += 1
    elif change == "catalog":
        host.index = ModIndex()
    elif change == "loaded":
        host.index.loaded = True
    elif change == "loc_target":
        host.edit_loc_file = "other.yml"
    elif change == "loc_language":
        host.app_config.loc_language = "french"
    else:
        monkeypatch.setattr(validation_ui, "get_language", lambda: "changed-language")
    host.controller.schedule()
    host.fire()
    _finish(tasks)
    assert captures.call_count == 2
    assert len(host.applied) == 2


def test_localisation_file_changes_are_polled_without_content_reads_on_tk(
    dispatch, tmp_path
):
    host, tasks, captures, loc_reads, _ = dispatch
    path = tmp_path / "loc.yml"
    host.edit_loc_file = str(path)
    host.controller.run()
    _finish(tasks)
    host.controller.start()
    for content in ('l_english:\n A:0 "first"', 'l_english:\n A:0 "different"', None):
        if content is None:
            path.unlink()
        else:
            path.write_text(content)
        old_reads = loc_reads.call_count
        host.fire(1000)
        host.fire()
        assert loc_reads.call_count == old_reads
        _finish(tasks)
    assert captures.call_count == 4
    assert loc_reads.call_count == 4


def test_many_edits_in_flight_capture_only_the_latest_follow_up(dispatch):
    host, tasks, captures, _, _ = dispatch
    host.controller.run()
    for number in range(10):
        host.focuses[1].name = str(number)
        host.focuses.mark_content_changed()
        host.controller.schedule()
    assert captures.call_count == 1
    assert len(tasks) == 1
    _finish(tasks)
    assert host.applied == []
    host.fire()
    assert captures.call_count == 2
    assert captures.call_args.args[0][1].name == "9"
    _finish(tasks)
    assert len(host.applied) == 1
    assert host.jobs == {}


def test_explicit_refresh_bypasses_completed_key_and_coalesces_in_flight(dispatch):
    host, tasks, captures, _, _ = dispatch
    host.controller.run()
    _finish(tasks)
    host.controller.run(force=True)
    for _ in range(10):
        host.controller.run(force=True)
    assert captures.call_count == 2
    _finish(tasks)
    assert len(tasks) == 1
    assert captures.call_count == 3
    _finish(tasks)
    assert host.jobs == {}


def test_failed_worker_releases_slot_and_explicit_retry_is_retained(dispatch):
    host, tasks, captures, _, _ = dispatch
    host.controller.run()
    host.controller.run(force=True)
    _, _, fail = tasks.pop(0)
    fail(OSError("failed read"))
    assert len(tasks) == 1
    _finish(tasks)
    assert captures.call_count == 2
    assert len(host.applied) == 1


def test_shutdown_cancels_pending_checks_and_discards_late_results(dispatch):
    host, tasks, captures, _, _ = dispatch
    host.controller.start()
    host.fire()
    host._lifecycle.close()
    _finish(tasks)
    host.controller.schedule()
    host.controller.run(force=True)
    assert host.applied == []
    assert host.jobs == {}
    assert captures.call_count == 1
