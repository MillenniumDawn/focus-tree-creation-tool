"""New decision wizard records get fresh uuid uids distinct from restored dm ids."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from hoi4cm.wizards.decision import (
    dedup_decision_state,
    restore_decision_autosave,
    restore_decision_state,
    serialize_decision_state,
    snapshot_decision_state,
)


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
