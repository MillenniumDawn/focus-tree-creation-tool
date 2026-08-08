import importlib
import os
import pkgutil
import subprocess
import sys
from pathlib import Path

import hoi4cm


def test_all_hoi4cm_submodules_import_cleanly():
    failures = []
    walker = pkgutil.walk_packages(
        hoi4cm.__path__, hoi4cm.__name__ + ".", onerror=failures.append
    )
    for info in walker:
        try:
            importlib.import_module(info.name)
        except Exception as e:
            failures.append(f"{info.name}: {e!r}")

    assert not failures, failures


def _run_in_subprocess(code):
    # Monolith lives at repo root and inserts src/ onto sys.path itself on import.
    repo_root = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([repo_root, *sys.path])}
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )


def test_hoi4_content_maker_imports_in_subprocess():
    result = _run_in_subprocess("import hoi4_content_maker")
    assert result.returncode == 0, result.stderr


def test_startup_does_not_import_wizard_modules():
    """A launch that never opens a wizard must not pay for the wizard modules.

    `ui/mod_loading.py` imports `hoi4cm.wizards._shared` at module scope, so
    an eager `wizards/__init__.py` drags all five wizards (~12k lines) back
    into startup and silently undoes the lazy menu-callback imports.
    """
    result = _run_in_subprocess(
        "import sys, hoi4_content_maker; "
        "print('WIZARDS:' + ','.join("
        "sorted(m for m in sys.modules if m.startswith('hoi4cm.wizards.'))))"
    )
    assert result.returncode == 0, result.stderr
    # The app logs to stdout on import, so pick the marker line out.
    line = next(x for x in result.stdout.splitlines() if x.startswith("WIZARDS:"))
    loaded = [m for m in line.removeprefix("WIZARDS:").split(",") if m]
    assert loaded == ["hoi4cm.wizards._shared"], loaded


def test_lazy_wizards_are_declared_as_pyinstaller_hiddenimports():
    """The lazy `__getattr__` leaves no static edge for PyInstaller to follow.

    Without an explicit hiddenimports entry the wizard modules are dropped
    from the frozen build and every wizard menu item raises at runtime — a
    failure the build job cannot see, since the binary still links.
    """
    import hoi4cm.wizards as wizards

    spec = (Path(__file__).resolve().parent.parent / "build" / "build.py").read_text()
    missing = [
        mod
        for mod in wizards._WIZARD_MODULES.values()
        if f"'hoi4cm.wizards.{mod}'" not in spec
    ]
    assert not missing, missing
