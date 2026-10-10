"""New decision wizard records get fresh uuid uids distinct from restored dm ids."""

from __future__ import annotations

import copy
import json
import tkinter as tk
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

import hoi4cm.wizards.decision as decision_mod
from hoi4cm.mod import MOD
from hoi4cm.wizards.decision import (
    dedup_decision_state,
    restore_decision_autosave,
    restore_decision_state,
    serialize_decision_state,
    snapshot_decision_state,
)

# ── shared isolation fixture ─────────────────────────────────────────────────


class _WizardEnv:
    """Test-local handle on the isolated autosave location and prompt calls."""

    def __init__(self, tmp_path: Path):
        self.autosave_file = tmp_path / "decision.json"
        self.prompts: list[str] = []

    def write_autosave(self, payload: dict[str, Any]) -> None:
        self.autosave_file.write_text(json.dumps(payload), encoding="utf-8")

    def read_autosave(self) -> dict[str, Any]:
        text = self.autosave_file.read_text(encoding="utf-8")
        payload: dict[str, Any] = json.loads(text)
        return payload


@pytest.fixture(autouse=True)
def decision_ids_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_WizardEnv]:
    """Isolate the autosave location, message boxes, and MOD edit-target state.

    Mirrors the isolation style of ``tests/test_wizard_decision.py``: MOD's
    edit-target fields are snapshotted and restored because the wizard's
    import path writes them back.
    """
    monkeypatch.setattr(
        decision_mod, "autosave_path", lambda name: str(tmp_path / name)
    )
    env = _WizardEnv(tmp_path)

    def _accept(*args: Any, **kwargs: Any) -> bool:
        env.prompts.append(str(args[0] if args else ""))
        return True

    def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr("tkinter.messagebox.askyesno", _accept)
    monkeypatch.setattr("tkinter.messagebox.showinfo", _noop)
    monkeypatch.setattr("tkinter.messagebox.showwarning", _noop)
    monkeypatch.setattr("tkinter.messagebox.showerror", _noop)

    snapshot = copy.deepcopy(MOD.__dict__)
    MOD.loaded = False
    MOD.root = None
    MOD.edit_decisions_file = ""
    MOD.edit_decisions_cat_file = ""
    MOD.edit_loc_file = ""
    MOD.edit_scripted_loc_file = ""
    try:
        yield env
    finally:
        MOD.__dict__.clear()
        MOD.__dict__.update(snapshot)


@pytest.fixture()
def capture_wizard_timers(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[int, Callable[..., Any]]]:
    """Capture Toplevel ``after`` callbacks without scheduling any timer.

    With nothing scheduled, deferred preview rebuilds never render (rendering
    them crashed this box's Xwayland with BadAlloc), and each test invokes the
    captured callback it needs at a deterministic point.
    """
    captured: list[tuple[int, Callable[..., Any]]] = []

    def _capture_after(
        self: tk.Misc, ms: float, func: Callable[..., Any], *args: Any
    ) -> str:
        captured.append((int(ms), func))
        return f"captured-after-{len(captured)}"

    monkeypatch.setattr(tk.Toplevel, "after", _capture_after, raising=False)
    return captured


# ── Tk helpers ───────────────────────────────────────────────────────────────


def _button_by_text(root: tk.Tk, needle: str) -> tk.Button | None:
    stack: list[tk.Misc] = [root]
    while stack:
        widget: tk.Misc = stack.pop()
        if isinstance(widget, tk.Button) and needle in widget.cget("text"):
            return widget
        stack.extend(widget.winfo_children())
    return None


def _wizard_window(root: tk.Tk) -> tk.Toplevel:
    for child in root.winfo_children():
        if isinstance(child, tk.Toplevel):
            return child
    raise AssertionError("decision wizard window was not created")


def _sole_captured(
    captured: list[tuple[int, Callable[..., Any]]], name: str
) -> Callable[..., Any]:
    """Return the one captured wizard callback whose qualname ends with ``name``."""
    matches = [
        func
        for _ms, func in captured
        if getattr(func, "__qualname__", "").endswith(name)
    ]
    assert len(matches) == 1, f"expected one captured {name}, got {len(matches)}"
    return matches[0]


def _close_wizard(wizard: tk.Toplevel) -> None:
    """Invoke the wizard's WM_DELETE_WINDOW handler as a window manager would."""
    handler = wizard.tk.call("wm", "protocol", str(wizard), "WM_DELETE_WINDOW")
    assert handler, "decision wizard did not register WM_DELETE_WINDOW"
    wizard.tk.call(str(handler))


def _seed_dm_autosave(
    tk_root: tk.Tk, env: _WizardEnv, captured: list[tuple[int, Callable[..., Any]]]
) -> dict[str, Any]:
    """Write an autosave holding wizard-shaped records under dm_1/dm_2 uids.


    Records come from a first, disposable wizard session, so their shape
    always matches what the serializer persists; only the uids are rewritten.
    """
    decision_mod.open_decision_wizard(tk_root)
    new_cat = _button_by_text(tk_root, "New Category")
    assert new_cat is not None
    new_cat.invoke()
    new_dec = _button_by_text(tk_root, "New Decision")
    assert new_dec is not None
    new_dec.invoke()
    _close_wizard(_wizard_window(tk_root))
    captured.clear()  # drop the seed session's callbacks; tests invoke their own
    env.prompts.clear()
    payload = env.read_autosave()
    payload["cats"][0]["uid"] = "dm_1"
    payload["decs"][0]["uid"] = "dm_2"
    payload["decs"][0]["cat_uid"] = "dm_1"
    return payload


# ── headless regression coverage (restores records holding dm_1) ─────────────


def _cat_record(uid: str, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {"uid": uid, "cat_id": "TAG_restored", "_extras": []}
    record.update(extra)
    return record


def _dec_record(uid: str, cat_uid: str, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "uid": uid,
        "cat_uid": cat_uid,
        "dec_id": "TAG_restored_decision",
        "_extras": [],
    }
    record.update(extra)
    return record


def _lookup_category(
    cats: Iterable[Mapping[str, Any]], cat_uid: object
) -> Mapping[str, Any] | None:
    """Mirror the wizard's ``_get_cat`` lookup shape."""
    return next((c for c in cats if c["uid"] == cat_uid), None)


def test_new_records_after_restored_autosave_get_fresh_uids():
    # Imported per-test so this module also collects on trees without the
    # extracted factories, keeping the pre-fix duplicate-uid failure runnable.
    from hoi4cm.wizards.decision import (
        new_category_record,
        new_decision_record,
    )

    cats: list[dict[str, Any]] = []
    decs: list[dict[str, Any]] = []
    persisted = serialize_decision_state(
        [_cat_record("dm_1")], [_dec_record("dm_2", "dm_1")]
    )

    saved = restore_decision_autosave(json.loads(json.dumps(persisted)))
    assert saved is not None
    restore_decision_state(cats, decs, saved)
    assert [c["uid"] for c in cats] == ["dm_1"]
    assert [d["uid"] for d in decs] == ["dm_2"]

    new_cat = new_category_record()
    new_dec = new_decision_record(cat_uid=new_cat["uid"])
    dec_on_restored = new_decision_record(cat_uid="dm_1")

    fresh_uids = [new_cat["uid"], new_dec["uid"], dec_on_restored["uid"]]
    assert all(uid not in ("dm_1", "dm_2") for uid in fresh_uids)
    assert len(set(fresh_uids)) == len(fresh_uids) == 3

    merged_cats = cats + [new_cat]
    merged_decs = decs + [new_dec, dec_on_restored]
    unique_cats, kept_decs = dedup_decision_state(merged_cats, merged_decs)
    assert [c["uid"] for c in unique_cats] == [c["uid"] for c in merged_cats]
    assert [d["uid"] for d in kept_decs] == [d["uid"] for d in merged_decs]
    assert _lookup_category(unique_cats, dec_on_restored["cat_uid"]) is cats[0]
    assert _lookup_category(unique_cats, new_dec["cat_uid"]) is new_cat


def test_new_records_after_undo_restore_get_fresh_uids():
    from hoi4cm.wizards.decision import (
        new_category_record,
        new_decision_record,
    )

    cats: list[dict[str, Any]] = []
    decs: list[dict[str, Any]] = []
    snapshot = snapshot_decision_state(
        [_cat_record("dm_1")], [_dec_record("dm_2", "dm_1")]
    )

    restore_decision_state(cats, decs, snapshot)
    new_cat = new_category_record()
    new_dec = new_decision_record(cat_uid="dm_1")
    assert {new_cat["uid"], new_dec["uid"]}.isdisjoint({"dm_1", "dm_2"})
    unique_cats, kept_decs = dedup_decision_state(cats + [new_cat], decs + [new_dec])
    assert len(unique_cats) == 2 and len(kept_decs) == 2


def test_repeated_creation_never_repeats_a_uid():
    from hoi4cm.wizards.decision import (
        new_category_record,
        new_decision_record,
    )

    records = [new_category_record() for _ in range(16)] + [
        new_decision_record() for _ in range(16)
    ]
    uids = [record["uid"] for record in records]
    assert len(set(uids)) == len(records) == 32
    assert new_category_record()["uid"] not in set(uids)


def test_fresh_record_uid_survives_the_autosave_cycle():
    from hoi4cm.wizards.decision import (
        new_category_record,
        new_decision_record,
    )

    cat = new_category_record()
    dec = new_decision_record(cat_uid=cat["uid"])

    payload = json.loads(json.dumps(serialize_decision_state([cat], [dec])))
    restored = restore_decision_autosave(payload)
    assert restored is not None
    restored_cats, restored_decs = restored
    assert restored_cats[0]["uid"] == cat["uid"]
    assert restored_decs[0]["cat_uid"] == cat["uid"]

    after_restore = new_category_record()
    assert after_restore["uid"] != cat["uid"]
    assert dedup_decision_state(restored_cats + [after_restore], restored_decs) == (
        restored_cats + [after_restore],
        restored_decs,
    )


# ── end-to-end wizard wiring (real window, hidden by the shared fixture) ─────


def test_wizard_restore_then_new_records_keep_distinct_uids(
    tk_root: tk.Tk,
    decision_ids_env: _WizardEnv,
    capture_wizard_timers: list[tuple[int, Callable[..., Any]]],
) -> None:
    env = decision_ids_env
    env.write_autosave(_seed_dm_autosave(tk_root, env, capture_wizard_timers))

    decision_mod.open_decision_wizard(tk_root)
    _sole_captured(capture_wizard_timers, "_try_restore")()
    assert "Restore autosave" in env.prompts

    new_cat = _button_by_text(tk_root, "New Category")
    assert new_cat is not None
    new_cat.invoke()
    new_dec = _button_by_text(tk_root, "New Decision")
    assert new_dec is not None
    new_dec.invoke()

    _close_wizard(_wizard_window(tk_root))
    payload = env.read_autosave()

    cat_uids = [str(c["uid"]) for c in payload["cats"]]
    dec_uids = [str(d["uid"]) for d in payload["decs"]]

    # The restored records kept their persisted ids, exactly once each.
    assert cat_uids.count("dm_1") == 1
    assert dec_uids.count("dm_2") == 1
    # Both creations landed and no uid was reused.
    assert len(cat_uids) == 2 and len(dec_uids) == 2
    assert len(set(cat_uids + dec_uids)) == 4
    # Every decision's category link still resolves (wizard `_get_cat` shape).
    cat_uid_set = set(cat_uids)
    for dec in payload["decs"]:
        assert str(dec["cat_uid"]) in cat_uid_set


def test_wizard_import_after_restore_does_not_reuse_restored_uids(
    tk_root: tk.Tk,
    decision_ids_env: _WizardEnv,
    capture_wizard_timers: list[tuple[int, Callable[..., Any]]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = decision_ids_env
    env.write_autosave(_seed_dm_autosave(tk_root, env, capture_wizard_timers))

    decision_mod.open_decision_wizard(tk_root)
    _sole_captured(capture_wizard_timers, "_try_restore")()
    assert "Restore autosave" in env.prompts

    decisions_dir = tmp_path / "mod" / "common" / "decisions"
    decisions_dir.mkdir(parents=True)
    decisions_file = decisions_dir / "IMP_decisions.txt"
    decisions_file.write_text(
        "IMP_cat = {\n\tIMP_decision = {\n\t\tallowed = { always = yes }\n\t}\n}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tkinter.filedialog.askopenfilenames",
        lambda **kwargs: (str(decisions_file),),
    )

    import_button = _button_by_text(tk_root, "Import .txt")
    assert import_button is not None
    import_button.invoke()

    _close_wizard(_wizard_window(tk_root))
    payload = env.read_autosave()

    cat_uids = [str(c["uid"]) for c in payload["cats"]]
    dec_uids = [str(d["uid"]) for d in payload["decs"]]

    # The restored records survive the import and keep their persisted ids.
    assert cat_uids.count("dm_1") == 1
    assert dec_uids.count("dm_2") == 1
    # The imported block landed alongside them.
    assert "IMP_cat" in {str(c["cat_id"]) for c in payload["cats"]}
    assert "IMP_decision" in {str(d["dec_id"]) for d in payload["decs"]}
    # No uid was reused across restored and imported records.
    assert len(set(cat_uids)) == len(cat_uids)
    assert len(set(dec_uids)) == len(dec_uids)
    cat_uid_set = set(cat_uids)
    for dec in payload["decs"]:
        assert str(dec["cat_uid"]) in cat_uid_set
