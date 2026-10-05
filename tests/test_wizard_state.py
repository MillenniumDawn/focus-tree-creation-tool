"""Headless tests for the wizard state helpers in issue #165."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from hoi4cm.wizards.decision import (
    DECISION_UNDO_LIMIT,
    dedup_decision_state,
    push_decision_undo,
    restore_decision_autosave,
    restore_decision_state,
    serialize_decision_state,
    snapshot_decision_state,
)
from hoi4cm.wizards.event import (
    EVENT_AUTOSAVE_FIELDS,
    event_autosave_records,
    restore_event_autosave,
)
from hoi4cm.wizards.national_spirit import spirit_autosave_snapshot


def _cat(uid: str, cat_id: str = "TAG_one", **extra: Any) -> dict[str, Any]:
    record = {"uid": uid, "cat_id": cat_id, "_extras": []}
    record.update(extra)
    return record


def _dec(uid: str, cat_uid: str = "c1", **extra: Any) -> dict[str, Any]:
    record = {"uid": uid, "cat_uid": cat_uid}
    record.update(extra)
    return record


class _FreshEvent:
    uid: str

    def __init__(self, uid: str):
        self.uid = uid


class _Factory:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return _FreshEvent(f"fresh-{self.calls}")


class _EventRecord:
    """Event-record stand-in carrying the wizard's known fields."""

    eid = "my_namespace.1"
    etype = "country_event"
    extra = ""
    title_text = "Title"
    desc_text = "Desc"
    picture = "GFX_report_event_generic_handshake"
    major = False
    fire_once = False
    triggered = True
    hidden = False
    mtth_days = ""
    mtth_months = ""
    trigger_code = ""
    immediate = ""
    options = [{"name": "my_namespace.1.a", "text": "Option A"}]

    def __init__(self, **overrides):
        for key, value in overrides.items():
            setattr(self, key, value)


# Decision undo and autosave helpers


def test_decision_undo_depth_is_bounded_at_thirty():
    stack = []
    for index in range(DECISION_UNDO_LIMIT + 5):
        push_decision_undo(stack, [_cat(f"c{index}")], [_dec(f"d{index}", f"c{index}")])
    assert len(stack) == DECISION_UNDO_LIMIT
    assert stack[0][0][0]["uid"] == "c5"
    assert stack[-1][0][0]["uid"] == "c34"


def test_decision_undo_snapshots_isolate_nested_mutable_values():
    cats = [_cat("c1", _extras=[{"value": ["original"]}])]
    decs = [_dec("d1", details={"value": ["original"]})]
    snapshot = snapshot_decision_state(cats, decs)

    cats[0]["_extras"][0]["value"].append("live")
    decs[0]["details"]["value"].append("live")
    assert snapshot[0][0]["_extras"] == [{"value": ["original"]}]
    assert snapshot[1][0]["details"] == {"value": ["original"]}

    snapshot[0][0]["_extras"][0]["value"].append("snapshot")
    assert cats[0]["_extras"][0]["value"] == ["original", "live"]


def test_restore_decision_state_is_in_place_and_detached():
    cats = [_cat("live")]
    decs = [_dec("live-dec", "live")]
    cats_id, decs_id = id(cats), id(decs)
    snapshot = snapshot_decision_state([_cat("saved")], [_dec("saved-dec", "saved")])

    restore_decision_state(cats, decs, snapshot)
    assert id(cats) == cats_id and id(decs) == decs_id
    assert cats == [_cat("saved")]
    assert decs == [_dec("saved-dec", "saved")]
    cats[0]["_extras"].append("live edit")
    assert snapshot[0][0]["_extras"] == []


def test_restore_decision_state_rejects_malformed_snapshot_atomically():
    cats = [_cat("live")]
    decs = [_dec("live-dec", "live")]
    before = (snapshot_decision_state(cats, decs), id(cats), id(decs))

    with pytest.raises(ValueError, match="invalid decision snapshot"):
        restore_decision_state(cats, decs, ([_cat("saved")], [{"uid": "no-cat-uid"}]))

    assert (cats, decs) == before[0]
    assert id(cats) == before[1] and id(decs) == before[2]


def test_serialize_decision_state_is_detached_and_preserves_unknown_fields():
    cats = [_cat("c1", note={"nested": [1]})]
    decs = [_dec("d1", note={"nested": [2]})]
    payload = serialize_decision_state(cats, decs)

    cats[0]["note"]["nested"].append(3)
    decs[0]["note"]["nested"].append(4)
    assert payload == {
        "cats": [_cat("c1", note={"nested": [1]})],
        "decs": [_dec("d1", note={"nested": [2]})],
    }


def test_restore_decision_autosave_deduplicates_by_uid_and_drops_orphans():
    payload = {
        "cats": [
            _cat("c1", "TAG_same", note="first"),
            _cat("c1", "TAG_duplicate", note="duplicate uid"),
            _cat("c2", "TAG_same", note="distinct uid"),
        ],
        "decs": [
            _dec("d1", "c1", unknown_field={"keep": True}),
            _dec("d2", "c2"),
            _dec("orphan", "missing"),
        ],
        "older_build_field": "preserved by source payload",
    }

    restored = restore_decision_autosave(payload)
    assert restored is not None
    assert restored == (
        [
            _cat("c1", "TAG_same", note="first"),
            _cat("c2", "TAG_same", note="distinct uid"),
        ],
        [_dec("d1", "c1", unknown_field={"keep": True}), _dec("d2", "c2")],
    )
    assert restored[0][0] is not payload["cats"][0]
    assert len(payload["cats"]) == 3 and len(payload["decs"]) == 3


def test_decision_autosave_json_round_trip_keeps_extra_fields():
    payload = serialize_decision_state(
        [_cat("c1", "TAG_é", old_field=["kept"])],
        [_dec("d1", old_decision_field={"nested": True})],
    )
    restored = restore_decision_autosave(json.loads(json.dumps(payload)))
    assert restored is not None
    assert restored == (payload["cats"], payload["decs"])


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"cats": [], "decs": []},
        {"cats": 1, "decs": []},
        {"cats": [_cat("c1")], "decs": "bad"},
        {"cats": [1], "decs": []},
        {"cats": [{"uid": "c1"}], "decs": []},
        {"cats": [_cat("c1")], "decs": [{"uid": "d1"}]},
        {"cats": [], "decs": [_dec("orphan", "missing")]},
    ],
)
def test_malformed_or_empty_decision_autosave_is_not_restorable(payload):
    live_cats = [_cat("live")]
    live_decs = [_dec("live-dec", "live")]
    before = snapshot_decision_state(live_cats, live_decs)

    assert restore_decision_autosave(payload) is None
    assert (live_cats, live_decs) == before


def test_decision_dedup_is_non_mutating_and_keeps_same_cat_id():
    cats = [_cat("c1", "TAG_one"), _cat("c1", "TAG_one"), _cat("c2", "TAG_one")]
    decs = [_dec("d1", "c1"), _dec("orphan", "gone")]

    unique_cats, kept_decs = dedup_decision_state(cats, decs)
    assert [cat["uid"] for cat in unique_cats] == ["c1", "c2"]
    assert unique_cats[0] is cats[0]
    assert [dec["uid"] for dec in kept_decs] == ["d1"]
    assert len(cats) == 3 and len(decs) == 2


# Event autosave helpers


def test_event_serializer_writes_known_fields_in_stable_order():
    event = _EventRecord()
    event.extra = "not part of the current writer format"
    records = event_autosave_records([event])

    assert list(records[0]) == list(EVENT_AUTOSAVE_FIELDS)
    assert records[0]["eid"] == "my_namespace.1"
    assert "extra" not in records[0]
    assert records[0]["options"] == event.options
    assert records[0]["options"] is not event.options


def test_event_restoration_preserves_unknown_fields_and_detaches_nested_data():
    payload = [{"eid": "older.1", "options": [{"effects": ["original"]}], "legacy": 7}]
    factory = _Factory()
    restored = restore_event_autosave(payload, factory)
    assert restored is not None

    assert factory.calls == 1
    assert restored[0].uid == "fresh-1"
    assert restored[0].eid == "older.1"
    assert restored[0].options == [{"effects": ["original"]}]
    assert restored[0].legacy == 7
    restored[0].options[0]["effects"].append("new")
    assert payload[0]["options"][0]["effects"] == ["original"]


@pytest.mark.parametrize("invalid_record", [{"__class__": "invalid"}, {"__dict__": 1}])
def test_event_restore_rejects_attribute_errors_without_partial_replacement(
    invalid_record,
):
    factory = _Factory()
    live_events = [_FreshEvent("live")]
    original = live_events[0]
    payload = [{"eid": "valid-first-record"}, invalid_record]

    restored = restore_event_autosave(payload, factory)
    if restored is not None:
        live_events[:] = restored

    assert restored is None
    assert factory.calls == 2
    assert live_events == [original]
    assert live_events[0] is original


def test_event_restore_preserves_saved_uid_over_fresh_uid():
    restored = restore_event_autosave([{"uid": "saved-uid"}], _Factory())
    assert restored is not None
    assert restored[0].uid == "saved-uid"


def test_event_restoration_keeps_older_records_with_missing_known_fields():
    restored = restore_event_autosave(
        [{"eid": "legacy.1", "legacy": "kept"}], _Factory()
    )
    assert restored is not None
    assert restored[0].eid == "legacy.1"
    assert restored[0].legacy == "kept"


@pytest.mark.parametrize("payload", [None, [], {}, [1], [{"ok": 1}, None]])
def test_malformed_or_empty_event_autosave_is_not_restorable(payload):
    assert restore_event_autosave(payload, _Factory()) is None


# National-spirit autosave snapshot


def test_spirit_snapshot_takes_collected_values_and_deep_copies_modifiers():
    values = {"mod_id": "MD", "loc_name": "Gründung"}
    modifiers: list[dict[str, Any]] = [
        {"key": "stability_weekly", "value": "0.1", "nested": ["a"]}
    ]
    snapshot = cast(dict[str, Any], spirit_autosave_snapshot(values, modifiers))

    values["mod_id"] = "changed"
    modifiers[0]["nested"].append("live")
    snapshot["modifiers"][0]["nested"].append("snapshot")
    assert snapshot["mod_id"] == "MD"
    assert snapshot["loc_name"] == "Gründung"
    assert snapshot["modifiers"][0]["nested"] == ["a", "snapshot"]
    assert modifiers[0]["nested"] == ["a", "live"]


def test_spirit_snapshot_accepts_empty_state():
    assert spirit_autosave_snapshot({}, []) == {"modifiers": []}
