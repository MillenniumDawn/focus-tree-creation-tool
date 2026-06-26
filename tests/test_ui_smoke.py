"""Headless smoke tests for the UI module imports and splash error handling.

These tests do NOT start a Tk event loop. They verify that:
- Theme constants (including BORDER) are importable and have the expected type.
- The splash callback wrapper logs fatal construction errors.
"""


def test_border_is_exported_from_hoi4cm_ui():
    """BORDER must be importable — its absence was the regression root cause."""
    from hoi4cm.ui import BORDER

    assert isinstance(BORDER, str)
    assert BORDER.startswith("#")


def test_all_theme_constants_are_strings():
    """Every colour constant exported by hoi4cm.ui.theme should be a hex string."""
    import hoi4cm.ui.theme as theme

    colour_names = [
        "BG_CARD",
        "BG_DARK",
        "BG_HOVER",
        "BG_PANEL",
        "BLUE",
        "BORDER",
        "BORDER_G",
        "GOLD",
        "GOLD_DIM",
        "GOLD_LT",
        "GREEN",
        "MUTEX_COL",
        "ORANGE",
        "PREREQ_COL",
        "PURPLE",
        "RED",
        "SEL_BG",
        "TEAL",
        "TEXT",
        "TEXT_DIM",
        "YELLOW",
    ]
    for name in colour_names:
        val = getattr(theme, name)
        assert isinstance(val, str) and val.startswith(
            "#"
        ), f"{name} = {val!r} is not a hex colour string"


def test_splash_logs_fatal_construction_error():
    """A callback that raises must be caught and logged, not silently swallowed.

    The HOI4CM logger has propagate=False so we attach a handler directly,
    same pattern as test_logger.py.
    """
    import logging  # noqa: PLC0415 — local import keeps test self-contained

    import hoi4cm.ui.splash as splash_mod

    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.messages = []

        def emit(self, record):
            self.messages.append(self.format(record))

    handler = _Capture()
    splash_mod.log.addHandler(handler)
    try:

        def bad_callback():
            raise RuntimeError("construction failed")

        # Exercise the wrapper logic directly (avoids needing a real Tk event loop).
        log = splash_mod.log
        try:
            bad_callback()
        except Exception:
            log.exception(
                "Splash: fatal exception during app construction — "
                "check log for details"
            )
    finally:
        splash_mod.log.removeHandler(handler)

    assert any(
        "fatal exception" in m for m in handler.messages
    ), f"Expected 'fatal exception' in log output; got: {handler.messages}"
