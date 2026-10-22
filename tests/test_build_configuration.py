"""Regression coverage for the generated PyInstaller spec and build pins."""

import ast
import importlib.util
import re
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIZARD_MODULES = (
    "national_spirit",
    "decision",
    "dyn_mod",
    "additional_income",
    "event",
    "character",
)
DEAD_ENCRYPTED_BUILD_FILES = (
    ROOT / "build" / "patch_spec_encrypted.py",
    ROOT / "build" / "build_encrypted.bat",
)


def _load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_script", ROOT / "build" / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _locked_version(package):
    requirements = (ROOT / "build" / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(package)}==([^\s\\]+)", requirements, re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_build_fallbacks_match_hashed_requirements():
    build_script = _load_build_script()
    pillow = _locked_version("pillow")
    pyinstaller = _locked_version("pyinstaller")

    assert build_script.PILLOW_REQUIREMENT == f"Pillow=={pillow}"
    assert build_script.PYINSTALLER_REQUIREMENT == f"pyinstaller=={pyinstaller}"


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
    assets_path = str(tmp_path / "src" / "hoi4cm" / "ui" / "assets").replace("\\", "/")
    analysis = next(
        node
        for node in ast.walk(ast.parse(content))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Analysis"
    )
    datas = next(
        keyword.value for keyword in analysis.keywords if keyword.arg == "datas"
    )
    assert ast.literal_eval(datas) == [
        (locales_path, "locales"),
        (assets_path, "hoi4cm/ui/assets"),
    ]
    assert all(f"'hoi4cm.wizards.{name}'" in content for name in WIZARD_MODULES)


def test_bundled_focus_actions_have_png_assets():
    assets = ROOT / "src" / "hoi4cm" / "ui" / "assets"
    for action, _label in import_module("hoi4cm.ui.focus_actions").ACTIONS:
        image = assets / f"{action}.png"
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), image


def test_bundled_sidebar_symbols_have_transparent_png_assets():
    import struct

    assets = ROOT / "src" / "hoi4cm" / "ui" / "assets" / "sidebar"
    names = (
        "nav_focus_trees",
        "nav_decisions",
        "nav_events",
        "nav_ideas",
        "nav_dynamic_modifiers",
        "project_folder_closed",
        "project_folder_open",
        "file_focus_tree",
        "item_focus",
        "file_localization",
        "file_graphics",
        "file_scripted_effects",
        "file_generic",
        "chevron_down",
        "chevron_right",
        "sidebar_collapse",
        "sidebar_expand",
    )
    for name in names:
        data = (assets / f"{name}.png").read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", data[16:24]) == (256, 256)
        assert data[25] == 6  # RGBA; UI backgrounds are not baked into symbols.


def test_encrypted_build_path_is_removed_and_cipher_stays_disabled():
    assert all(not path.exists() for path in DEAD_ENCRYPTED_BUILD_FILES)

    build_sources = [
        path.read_text(encoding="utf-8")
        for path in (ROOT / "build").rglob("*")
        if path.is_file() and path.suffix in {".bat", ".py", ".spec"}
    ]
    assert not any("ENCRYPTION_KEY" in content for content in build_sources)

    cipher_lines = [
        line.strip()
        for content in build_sources
        for line in content.splitlines()
        if "block_cipher" in line
    ]
    assert cipher_lines
    assert set(cipher_lines) == {"block_cipher = None"}

    for doc_path in (ROOT / "README.md", ROOT / "BUILD_INSTRUCTIONS.md"):
        doc = doc_path.read_text(encoding="utf-8")
        assert "build_encrypted" not in doc
        assert "--encrypted" not in doc


def test_stable_build_checks_tag_against_project_before_compiling():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    build = workflow.split("\n  build:\n", 1)[1].split("\n  release:\n", 1)[0]
    check = "python scripts/versioning.py check-release-tag"

    assert check in build
    assert "RELEASE_TAG: ${{ github.ref_name }}" in build
    assert "startsWith(github.ref, 'refs/tags/v')" in build
    assert "!contains(github.ref_name, '-pre.')" in build
    assert (
        "if: github.event_name == 'pull_request' || "
        "startsWith(github.ref, 'refs/tags/v')" in build
    )
    check_step = build.split("      - name: Check the release tag\n", 1)[1].split(
        "      - name:", 1
    )[0]
    assert "shell: bash" in check_step
    assert '"$RELEASE_TAG"' in check_step
    assert build.index(check) < build.index("python build/build.py")
