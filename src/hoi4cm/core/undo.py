"""Sparse undo stack: snapshot only the focuses an edit actually touches.

The old design deep-copied every loaded focus on every push (`_snapshot` in
the monolith). On a several-hundred-focus tree that's a lot of CPU and
retained memory for a 60-entry deque, most of which is never looked at again.

This module has no opinion on what a "focus" is beyond ``to_dict()``/a
factory to rebuild one from a dict, and it never imports tkinter, so it can
be pushed and popped in a plain unit test with no display.
"""

import copy
import json
import zlib
from collections import deque

_FULL = "full"
_SPARSE = "sparse"


class UndoStack:
    """A bounded stack of undo entries, each either sparse or a full snapshot.

    Entries are ``(label, kind, payload, id_set)``:
      - ``kind == "sparse"``: ``payload`` is ``{fid: focus_dict}`` for just
        the focuses the pushed action is about to mutate or delete.
      - ``kind == "full"``: ``payload`` is a zlib-compressed JSON blob of
        every focus at push time, for the rare bulk-operation case where
        the touched set isn't known (or is "all of them" anyway).

    ``id_set`` is the frozenset of every focus id present at push time, used
    on undo to spot ids the action created (present now, absent from
    ``id_set``) so they can be deleted without ever having been snapshotted.
    """

    def __init__(self, maxlen=60):
        self._stack = deque(maxlen=maxlen)

    def __len__(self):
        return len(self._stack)

    def clear(self):
        self._stack.clear()

    def push(self, label, focuses, touched_ids=None):
        """Save enough state to undo an action about to run on ``focuses``.

        Call this BEFORE mutating ``focuses``. ``touched_ids`` lists the ids
        the action is about to mutate or delete; ids the action only creates
        should be left out (undo deletes them via the ``id_set`` diff
        instead). Pass ``touched_ids=None`` when the touched set isn't known
        or would be "most of the tree anyway" (bulk import/clear): this takes
        a full compressed snapshot instead.
        """
        id_set = frozenset(focuses.keys())
        if touched_ids is None:
            blob = zlib.compress(
                json.dumps(
                    {str(fid): f.to_dict() for fid, f in focuses.items()}
                ).encode("utf-8")
            )
            self._stack.append((label, _FULL, blob, id_set))
            return
        touched = {
            fid: copy.deepcopy(focuses[fid].to_dict())
            for fid in touched_ids
            if fid in focuses
        }
        self._stack.append((label, _SPARSE, touched, id_set))

    def undo(self, focuses, focus_factory):
        """Pop the last entry and restore it into ``focuses`` in place.

        ``focus_factory`` rebuilds a focus object from a stored dict (e.g.
        ``Focus.from_dict``); it must preserve the dict's ``id``.

        Returns ``None`` if the stack was empty, otherwise
        ``(label, changed_ids, removed_ids)``: ``changed_ids`` were
        created/overwritten in ``focuses`` and need a redraw, ``removed_ids``
        were deleted and need their canvas items cleaned up.
        """
        if not self._stack:
            return None
        label, kind, payload, id_set = self._stack.pop()

        created_ids = [fid for fid in focuses if fid not in id_set]
        for fid in created_ids:
            del focuses[fid]

        if kind == _FULL:
            # id_set was captured from the same `focuses` dict the snapshot
            # came from, so it's exactly the snapshot's keys: created_ids
            # (current ids missing from id_set) already covers everything
            # that needs removing, there's nothing else to diff.
            snapshot = json.loads(zlib.decompress(payload).decode("utf-8"))
            snapshot = {int(k): v for k, v in snapshot.items()}
            changed_ids = set(snapshot)
            for fid, fd in snapshot.items():
                focuses[fid] = focus_factory(fd)
            return label, changed_ids, set(created_ids)

        changed_ids = set()
        for fid, fd in payload.items():
            focuses[fid] = focus_factory(fd)
            changed_ids.add(fid)
        removed_ids = set(created_ids)
        return label, changed_ids, removed_ids
