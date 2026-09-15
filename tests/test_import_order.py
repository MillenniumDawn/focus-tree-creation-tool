import os
import subprocess
import sys


def _run_imports(source):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_core_import_does_not_load_ui_or_tkinter():
    _run_imports(
        "import sys; import hoi4cm.core as core; "
        "assert not hasattr(core, 'check_tk_startup'); "
        "assert not hasattr(core, 'show_splash'); "
        "assert 'tkinter' not in sys.modules; "
        "assert '_tkinter' not in sys.modules; "
        "assert 'hoi4cm.core.image' not in sys.modules; "
        "assert 'PIL' not in sys.modules; "
        "assert 'PIL.Image' not in sys.modules; "
        "assert 'PIL.ImageTk' not in sys.modules; "
        "assert not any(name == 'hoi4cm.ui' or name.startswith('hoi4cm.ui.') "
        "for name in sys.modules)"
    )


def test_ui_import_before_core_has_no_cycle():
    _run_imports("import hoi4cm.ui; import hoi4cm.core")


def test_core_import_before_ui_has_no_cycle():
    _run_imports("import hoi4cm.core; import hoi4cm.ui")
