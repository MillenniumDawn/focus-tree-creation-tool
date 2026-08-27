"""Sparse undo stack with a paired redo stack: snapshot only the focuses an
edit actually touches.

The old design deep-copied every loaded focus on every push (`_snapshot` in
the monolith). On a several-hundred-focus tree that's a lot of CPU and
retained memory for a 60-entry deque, most of which is never looked at again.

This module has no opinion on what a "focus" is beyond ``to_dict()``/a
factory to rebuild one from a dict, and it never imports tkinter, so it can
be pushed and popped in a plain unit test with no display.

Redo
----
``push`` captures pre-state (the state to restore on undo). The first time
``undo`` is actually invoked we lazily snapshot the current (post-state)
focuses and stash it on the redo stack, matching the entry's own kind: sparse
entries capture just the touched ids, full entries still capture everything.
``redo`` restores it and mirrors the same capture back onto the undo stack.
A new ``push`` clears the redo stack; a new edit branch invalidates any redo
trail, matching every other editor's behavior.
"""

import copy
import json
import zlib
from collections import deque

_FULL = "full"
_SPARSE = "sparse"
_FOCUS_SEMANTIC_METADATA = (
    "_raw_gx",
    "_raw_gy",
    "_rel_dx",
    "_rel_dy",
    "_joint_extra",
    "_script_extras",
)


def _snapshot_focus(focus):
    """Return serializable focus state needed to restore an undo entry."""
    snapshot = copy.deepcopy(focus.to_dict())
    for attr in _FOCUS_SEMANTIC_METADATA:
        try:
            snapshot[attr] = copy.deepcopy(getattr(focus, attr))
        except AttributeError:
            continue
    return snapshot


def _decode_full(payload: bytes) -> dict[int, dict] | None:
    """Decompress a full-snapshot blob; None if the payload is corrupt."""
    try:
        snapshot = json.loads(zlib.decompress(payload).decode("utf-8"))
        if not isinstance(snapshot, dict):
            return None
        return {int(k): v for k, v in snapshot.items()}
    except zlib.error, UnicodeDecodeError, ValueError:
        return None


def _encode_full(focuses) -> bytes:
    """Compress every focus in ``focuses`` into a full-snapshot blob."""
    return zlib.compress(
        json.dumps({str(fid): _snapshot_focus(f) for fid, f in focuses.items()}).encode(
            "utf-8"
        )
    )


def _id_set(focuses) -> frozenset:
    """Cached id-set for a document, or a fresh frozenset for a plain dict."""
    cached = getattr(focuses, "id_set", None)
    if cached is not None:
        return cached
    return frozenset(focuses.keys())


class UndoStack:
    """A bounded undo stack with a paired redo stack.

    Undo entries are ``(label, kind, payload, id_set)``:
      - ``kind == "sparse"``: ``payload`` is ``{fid: focus_dict}`` for just
        the focuses the pushed action is about to mutate or delete.
      - ``kind == "full"``: ``payload`` is a zlib-compressed JSON blob of
        every focus at push time, for the rare bulk-operation case where
        the touched set isn't known (or is "all of them" anyway).

    ``id_set`` is the frozenset of every focus id present at push time, used
    on undo to spot ids the action created (present now, absent from
    ``id_set``) so they can be deleted without ever having been snapshotted.

    Redo entries are the same shape but the snapshot is taken lazily on
    the first ``undo``; see the module docstring.
    """

    def __init__(self, maxlen=60):
        self._stack: deque = deque(maxlen=maxlen)
        self._redo: deque = deque(maxlen=maxlen)

    def __len__(self):
        return len(self._stack)

    def clear(self):
        """Drop every entry from both stacks."""
        self._stack.clear()
        self._redo.clear()

    def push(self, label, focuses, touched_ids=None):
        """Save enough state to undo an action about to run on ``focuses``.

        Call this BEFORE mutating ``focuses``. ``touched_ids`` lists the ids
        the action is about to mutate or delete; ids the action only creates
        should be left out (undo deletes them via the ``id_set`` diff
        instead). Pass ``touched_ids=None`` when the touched set isn't known
        or would be "most of the tree anyway" (bulk import/clear): this takes
        a full compressed snapshot instead.

        ``focuses`` may be a plain dict or a ``FocusDocument``; the latter
        hands out a cached frozenset of its keys so consecutive pushes
        without structural changes share one object instead of reallocating
        a set of every id per action.

        A new edit branch invalidates the redo trail.
        """
        self._redo.clear()
        if touched_ids is None:
            self._stack.append((label, _FULL, _encode_full(focuses), _id_set(focuses)))
            return
        touched = {
            fid: _snapshot_focus(focuses[fid]) for fid in touched_ids if fid in focuses
        }
        self._stack.append((label, _SPARSE, touched, _id_set(focuses)))

    def undo(self, focuses, focus_factory):
        """Pop the last entry and restore it into ``focuses`` in place.

        Side effect: snapshot the current (post-state) focuses onto the
        redo stack, lazily, the first time undo is actually invoked. After
        that, ``redo`` can re-apply the action.

        Returns ``None`` if the stack was empty, otherwise
        ``(label, changed_ids, removed_ids)``: ``changed_ids`` were
        created/overwritten in ``focuses`` and need a redraw, ``removed_ids``
        were deleted and need their canvas items cleaned up.
        """
        if not self._stack:
            return None
        entry = self._stack[-1]
        self._redo.append(self._capture_counter(entry, focuses))
        self._stack.pop()
        return self._apply(entry, focuses, focus_factory)

    def redo(self, focuses, focus_factory):
        """Restore the state captured by the most recent ``undo``.

        Side effect: snapshot the current (post-undo) state back onto the
        undo stack as the next entry to undo, mirroring undo's lazy capture.

        Returns ``None`` if the redo stack was empty, otherwise
        ``(label, changed_ids, removed_ids)`` in the same shape as
        ``undo``.
        """
        if not self._redo:
            return None
        entry = self._redo[-1]
        self._stack.append(self._capture_counter(entry, focuses))
        self._redo.pop()
        return self._apply(entry, focuses, focus_factory)

    @staticmethod
    def _capture_counter(entry, focuses):
        """Snapshot ``focuses`` for the opposite stack, matching ``entry``'s
        own kind so undoing/redoing a sparse entry never full-encodes.

        For a sparse entry the relevant ids are the ones it touched, plus
        any ids created since (present now but absent from its ``id_set``,
        which ``_apply`` is about to delete) so the reverse trip can bring
        them back.
        """
        label, kind, payload, id_set = entry
        if kind == _FULL:
            return (label, _FULL, _encode_full(focuses), _id_set(focuses))
        touched = set(payload) | {fid for fid in focuses if fid not in id_set}
        snapshot = {
            fid: _snapshot_focus(focuses[fid]) for fid in touched if fid in focuses
        }
        return (label, _SPARSE, snapshot, _id_set(focuses))

    @staticmethod
    def _apply(entry, focuses, focus_factory):
        label, kind, payload, id_set = entry

        if kind == _FULL:
            # Decode before mutating anything: a corrupt blob (self-written
            # data, so effectively impossible) drops the entry without
            # damaging the document.
            snapshot = _decode_full(payload)
            if snapshot is None:
                return None
            # id_set was captured from the same `focuses` dict the snapshot
            # came from, so it's exactly the snapshot's keys: created_ids
            # (current ids missing from id_set) already covers everything
            # that needs removing, there's nothing else to diff.
            created_ids = [fid for fid in focuses if fid not in id_set]
            delete_many = getattr(focuses, "delete_many", None)
            if callable(delete_many):
                delete_many(created_ids, clean_references=False)
            else:
                for fid in created_ids:
                    del focuses[fid]
            changed_ids = set(snapshot)
            restored = [focus_factory(fd) for fd in snapshot.values()]
            load = getattr(focuses, "load", None)
            if callable(load):
                load(restored)
            else:
                for focus in restored:
                    focuses[focus.id] = focus
            return label, changed_ids, set(created_ids)

        created_ids = [fid for fid in focuses if fid not in id_set]
        delete_many = getattr(focuses, "delete_many", None)
        if callable(delete_many):
            delete_many(created_ids, clean_references=False)
        else:
            for fid in created_ids:
                del focuses[fid]

        changed_ids = set()
        restored = [focus_factory(fd) for fd in payload.values()]
        changed_ids.update(focus.id for focus in restored)
        extend = getattr(focuses, "extend", None)
        if callable(extend):
            extend(restored, replace=True)
        else:
            for focus in restored:
                focuses[focus.id] = focus
        removed_ids = set(created_ids)
        return label, changed_ids, removed_ids
