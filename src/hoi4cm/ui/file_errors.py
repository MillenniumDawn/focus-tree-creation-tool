"""One place to turn a failed mod-file write into something the user sees.

Exports write into the user's real mod, so a failure there is not a detail to
swallow: it goes into the in-app error log *and* raises a dialog naming the
file. The writes themselves are atomic (see
:mod:`hoi4cm.mod.workspace_files`), so "the export failed" always means the
targets still hold their previous contents — the message says so.
"""

import os

# Core *submodules*, not the facade: core/__init__ imports hoi4cm.ui before it
# binds these names (see tests/test_import_order.py).
from hoi4cm.core.i18n import tr
from hoi4cm.ui.error_report import report_error

__all__ = ["report_write_failure"]


def report_write_failure(parent, path, error, *, title=None):
    """Log a failed write against ``path`` and tell the user about it.

    ``parent`` is the window the dialog should belong to (``None`` for the
    default root). Returns the message shown, which is handy for tests and for
    callers that also want it in a status line.
    """
    name = os.path.basename(str(path)) or str(path)
    message = tr(
        "dialog.write_failed.body",
        "Could not write {file}:\n{error}\n\n"
        "The file was left unchanged — nothing was overwritten.",
        file=name,
        error=error,
    )
    report_error(
        message,
        error,
        parent=parent,
        title=title or tr("dialog.write_failed.title", "Write Failed"),
    )
    return message
