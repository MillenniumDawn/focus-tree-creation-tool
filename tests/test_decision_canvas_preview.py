"""Exercise deferred decision rendering and teardown in a bounded process."""

import json
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path

import pytest
from test_decision_preview import (
    _button_by_text,
    _ensure_dnd_available,
    _flush_after,
)

import hoi4cm.wizards.decision as decision_mod
from hoi4cm.mod import MOD

_CHILD_FLAG = "HOI4CM_DECISION_PREVIEW_CHILD"


def _widgets(root):
    stack = [root]
    while stack:
        widget = stack.pop()
        yield widget
        stack.extend(widget.winfo_children())


@pytest.mark.visible_tk
@pytest.mark.parametrize("mapped", [True, False], ids=["mapped", "withdrawn"])
@pytest.mark.parametrize("icon", ["none", "missing", "image"])
def test_decision_canvas_preview(tk_root, tmp_path, monkeypatch, request, mapped, icon):
    if os.environ.get(_CHILD_FLAG) != "1":
        tk_root.withdraw()
        report_path = tmp_path / "coverage.json"
        env = dict(os.environ)
        env[_CHILD_FLAG] = "1"
        env["COVERAGE_FILE"] = str(tmp_path / ".coverage")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-s",
                request.node.nodeid,
                "--cov=hoi4cm.wizards.decision",
                f"--cov-report=json:{report_path}",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "invalid command name" not in result.stderr
        report = json.loads(report_path.read_text(encoding="utf-8"))
        module = next(
            data
            for path, data in report["files"].items()
            if Path(path).name == "decision.py"
        )
        summary = module["functions"]["open_decision_wizard._build_preview"]["summary"]
        assert summary["covered_lines"] > 0
        return

    errors = []
    monkeypatch.setattr(
        tk_root, "report_callback_exception", lambda *args: errors.append(args)
    )
    monkeypatch.setattr(MOD, "loaded", False)
    monkeypatch.setattr(MOD, "root", None)
    monkeypatch.setattr(
        decision_mod, "autosave_path", lambda _name: str(tmp_path / "autosave.json")
    )
    _ensure_dnd_available()
    decision_mod.open_decision_wizard(tk_root)
    window = next(w for w in tk_root.winfo_children() if isinstance(w, tk.Toplevel))
    if not mapped:
        window.withdraw()
        tk_root.withdraw()
    for text in ("New Category", "New Decision"):
        button = _button_by_text(window, text)
        assert button is not None
        button.invoke()
    if icon != "none":
        label = next(
            w
            for w in _widgets(window)
            if isinstance(w, tk.Label) and w.cget("text") == "ICON"
        )
        entry = next(w for w in _widgets(label.master) if isinstance(w, tk.Entry))
        entry.insert(0, "test_preview")
        if icon == "image":
            assert decision_mod.PIL_OK
            path = tmp_path / "icon.png"
            image = tk.PhotoImage(master=tk_root, width=2, height=2)
            image.put("#ffffff", to=(0, 0, 2, 2))
            image.write(str(path), format="png")
            monkeypatch.setattr(MOD, "loaded", True)
            monkeypatch.setattr(MOD, "root", str(tmp_path))
            monkeypatch.setattr(
                MOD, "decision_sprites", {"GFX_decision_test_preview": str(path)}
            )
    for width in (1340, 900, 1600):
        window.geometry(f"{width}x820")
        preview = _button_by_text(window, "Preview")
        assert preview is not None
        preview.invoke()
        _flush_after(tk_root)
        assert bool(window.winfo_ismapped()) is mapped
        rendered = {
            w.get("1.0", "end").strip()
            for w in _widgets(window)
            if isinstance(w, tk.Text) and w.cget("bg") in ("#141929", "#161c2e")
        }
        assert {"My Category", "My Decision"} <= rendered
        assert all(
            w.winfo_reqwidth() <= 1340
            for w in _widgets(window)
            if isinstance(w, tk.Text) and w.cget("bg") in ("#141929", "#161c2e")
        )
        assert not errors
        if icon == "image":
            images = [
                w.cget("image")
                for w in _widgets(window)
                if isinstance(w, tk.Label) and w.cget("image")
            ]
            assert images
            assert any(
                (
                    int(tk_root.tk.call("image", "width", name)),
                    int(tk_root.tk.call("image", "height", name)),
                )
                == (24, 24)
                for name in images
            )
        else:
            assert any(
                isinstance(w, tk.Label) and w.cget("text") == "⚖"
                for w in _widgets(window)
            )
        code = _button_by_text(window, "Code")
        assert code is not None
        code.invoke()
        _flush_after(tk_root)
    preview = _button_by_text(window, "Preview")
    assert preview is not None
    preview.invoke()
    window.tk.call(window.protocol("WM_DELETE_WINDOW"))
    _flush_after(tk_root)
    assert not window.winfo_exists()
    assert not errors
