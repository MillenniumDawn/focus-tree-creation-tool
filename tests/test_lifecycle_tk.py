from __future__ import annotations

from hoi4cm.ui.lifecycle import ApplicationLifecycle


def test_delayed_tk_callback_fires_on_the_real_event_loop(tk_root) -> None:
    # Control for the cancel test below: without close(), one update() pass
    # is enough for a due callback to run.
    tk_root.withdraw()
    lifecycle = ApplicationLifecycle(tk_root)
    called: list[bool] = []
    lifecycle.after(tk_root, 0, lambda: called.append(True))

    tk_root.update()

    assert called == [True]


def test_close_cancels_delayed_tk_callback(tk_root) -> None:
    tk_root.withdraw()
    lifecycle = ApplicationLifecycle(tk_root)
    called: list[bool] = []
    lifecycle.after(tk_root, 0, lambda: called.append(True))

    lifecycle.close()
    tk_root.update()

    assert called == []
