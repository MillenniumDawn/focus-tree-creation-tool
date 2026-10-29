"""Headless coverage for the no-wait and withdrawn dialog paths."""

from hoi4cm.ui.widgets import grab_when_visible


class FakeWindow:
    """Minimal already-mapped or withdrawn Toplevel stand-in."""

    def __init__(self, *, state="normal", exists=True, viewable=True):
        self._state = state
        self._exists = exists
        self._viewable = viewable
        self.grabbed = False

    def winfo_exists(self):
        return self._exists

    def winfo_viewable(self):
        return self._viewable

    def state(self):
        return self._state

    def grab_set(self):
        self.grabbed = True


def test_viewable_window_is_grabbed_without_waiting():
    window = FakeWindow()

    assert grab_when_visible(window)
    assert window.grabbed


def test_withdrawn_live_window_is_left_for_builder_to_populate():
    window = FakeWindow(state="withdrawn", viewable=False)

    assert grab_when_visible(window)
    assert not window.grabbed


def test_destroyed_window_reports_cancellation():
    window = FakeWindow(exists=False, viewable=False)

    assert not grab_when_visible(window)
    assert not window.grabbed
