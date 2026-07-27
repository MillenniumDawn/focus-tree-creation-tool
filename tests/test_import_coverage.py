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


def test_hoi4_content_maker_imports_in_subprocess():
    # Monolith lives at repo root and inserts src/ onto sys.path itself on import.
    repo_root = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([repo_root, *sys.path])}
    result = subprocess.run(
        [sys.executable, "-c", "import hoi4_content_maker"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
