"""Preview error handling — dyn_mod parity for issue #63.

``dyn_mod.py`` had the opposite failure mode to ``national_spirit.py``:
no try at all, so a generator error surfaced as a Tk callback traceback
and never reached the in-app error log. The fix mirrors the national
spirit wizard: build first, log via ``add_error``/``get_logger``, narrow
widget errors to ``tk.TclError``.
"""

import pathlib
import re


def test_dyn_mod_preview_source_contains_expected_error_handling():
    src = pathlib.Path("src/hoi4cm/wizards/dyn_mod.py").read_text(encoding="utf-8")
    assert "text = _build_output()" in src
    assert "text = _dm_get_output()" in src
    assert "except tk.TclError:" in src
    assert "add_error" in src
    assert "get_logger" in src
    for name in ("def _preview", "def _dm_show_preview"):
        m = re.search(rf"{re.escape(name)}.*?def ", src, re.S)
        assert m, f"{name} block not found"
        block = m.group(0)
        assert "except tk.TclError" in block
        assert "except Exception as exc" in block
