"""Preview error handling — issue #63.

The national spirit wizard's live preview used to swallow generator failures
inside a broad ``except Exception: pass`` that also covered widget ops, leaving
stale or blank text with no signal. The fix builds text first, logs generator
failures via ``add_error``/``get_logger``, and narrows widget errors to
``tk.TclError``.

The headless generator cases live in
``test_wizard_generators_national_spirit.py``.
"""

import pathlib
import re


def test_preview_source_contains_expected_error_handling():
    """Regression guard: the fix must not be reverted to ``except Exception: pass``."""
    src = pathlib.Path("src/hoi4cm/wizards/national_spirit.py").read_text(
        encoding="utf-8"
    )
    # Build text before touching the widget.
    assert "text = _build_output()" in src
    # Widget ops are behind TclError only.
    assert "except tk.TclError:" in src
    # Generator failures are logged, not swallowed.
    assert "add_error" in src
    assert "get_logger" in src
    # Scope the check to the preview function: the old broad except over the
    # widget block must be gone there, even though other helpers still use it.
    m = re.search(r"def _refresh_preview.*?def _get_output_text", src, re.S)
    assert m, "_refresh_preview block not found"
    block = m.group(0)
    assert "except tk.TclError" in block
    assert "except Exception as exc" in block
    assert "except Exception:\n            pass" not in block
