"""Regression coverage for the standard and legacy PyInstaller specs."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIZARD_MODULES = (
    "national_spirit",
    "decision",
    "dyn_mod",
    "additional_income",
    "event",
)


def _load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_script", ROOT / "build" / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_spec_is_windowless_and_bundles_runtime_assets(tmp_path, monkeypatch):
    build_script = _load_build_script()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    monkeypatch.setattr(build_script, "SCRIPT_DIR", str(build_dir))
    monkeypatch.setattr(build_script, "ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(build_script, "SOURCE", str(tmp_path / "hoi4_content_maker.py"))
    monkeypatch.setattr(build_script.sys, "platform", "win32")

    generated = Path(build_script.write_spec())
    content = generated.read_text(encoding="utf-8")

    assert "    console=False," in content
    assert "    console=True," not in content
    locales_path = str(tmp_path / "locales").replace("\\", "/")
    assert f"datas=[({locales_path!r}, 'locales')]," in content
    assert all(f"'hoi4cm.wizards.{name}'" in content for name in WIZARD_MODULES)


def test_legacy_spec_is_windowless_and_bundles_runtime_assets():
    content = (ROOT / "build" / "hoi4_content_maker.spec").read_text(encoding="utf-8")

    assert "    console=False," in content
    assert "    console=True," not in content
    assert "    datas=[('..\\\\locales', 'locales')]," in content
    assert all(f"'hoi4cm.wizards.{name}'" in content for name in WIZARD_MODULES)
