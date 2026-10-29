"""Display text for undo-stack labels.

Labels pushed onto the undo stack stay English identifiers: the stack and the
extra-tree history match entries by label, so a label must not change with the
UI language. They are translated only when shown in the undo/redo toast.
"""

from __future__ import annotations

from collections.abc import Mapping

from hoi4cm.core.i18n import tr

UNDO_LABEL_KEYS: Mapping[str, str] = {
    "action": "undo.action",
    "add effect": "undo.add_effect",
    "add effect field": "undo.add_effect_field",
    "add focus": "undo.add_focus",
    "add mutex": "undo.add_mutex",
    "add offset": "undo.add_offset",
    "add prerequisite": "undo.add_prerequisite",
    "add prerequisite AND group": "undo.add_prerequisite_and_group",
    "add prerequisite OR group": "undo.add_prerequisite_or_group",
    "bulk_rename": "undo.bulk_rename",
    "change icon": "undo.change_icon",
    "clear all": "undo.clear_all",
    "delete focus": "undo.delete_focus",
    "delete selected": "undo.delete_selected",
    "draw.io import": "undo.drawio_import",
    "duplicate": "undo.duplicate",
    "edit effect": "undo.edit_effect",
    "edit focus": "undo.edit_focus",
    "edit focus code": "undo.edit_focus_code",
    "import tree": "undo.import_tree",
    "load extra tree": "undo.load_extra_tree",
    "load extra trees": "undo.load_extra_trees",
    "move focus": "undo.move_focus",
    "nudge focus": "undo.nudge_focus",
    "nudge focuses": "undo.nudge_focuses",
    "remove effect": "undo.remove_effect",
    "remove mutex": "undo.remove_mutex",
    "remove offset": "undo.remove_offset",
    "remove prerequisite group": "undo.remove_prerequisite_group",
    "rename effect field": "undo.rename_effect_field",
    "unload extra tree": "undo.unload_extra_tree",
}


def undo_label_text(label: str) -> str:
    """Return *label* in the UI language, or unchanged when it has no key."""
    key = UNDO_LABEL_KEYS.get(label)
    return label if key is None else tr(key, label)


__all__ = ["UNDO_LABEL_KEYS", "undo_label_text"]
