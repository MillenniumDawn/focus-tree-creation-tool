import os
import subprocess
import sys


def test_ui_import_before_core_facade_has_no_cycle():
    # core/__init__ imports hoi4cm.ui (for show_splash) before it binds the
    # tr / logger / paths names. That only holds because the ui import chain
    # reaches core *submodules* directly, never the core facade. Guard the
    # cycle in a fresh interpreter: importing ui first, then core, must work.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    result = subprocess.run(
        [sys.executable, "-c", "import hoi4cm.ui; import hoi4cm.core"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    assert result.returncode == 0, result.stderr
