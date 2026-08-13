"""Generic error reporter: in-app error log entry + file log + dialog.

``report_write_failure`` (:mod:`hoi4cm.ui.file_errors`) covers failed mod
writes, where the message has to promise the target file survived. Everything
else — a corrupt project file, an import/parse/export failure — lands here,
so a handled error stops disappearing the moment its dialog is dismissed.
"""

import traceback
from tkinter import messagebox

# Core *submodules*, not the facade: core/__init__ imports hoi4cm.ui before it
# binds these names (see tests/test_import_order.py).
from hoi4cm.core.i18n import tr
from hoi4cm.core.logger import add_error, get_logger

log = get_logger("errors")

__all__ = ["report_error"]


def report_error(msg, exc=None, *, parent=None, title=None):
    """Record ``msg`` (plus ``exc``'s traceback) and tell the user about it.

    Writes one entry to the in-app error log, one to the HOI4CM file log,
    then raises a dialog. Only real exceptions contribute a traceback; any
    other error object is ignored for it, so the reporter itself never
    raises. ``parent`` is the window the dialog should belong to (``None``
    for the default root). Returns the message shown, which is handy for
    tests and status lines.
    """
    entry = msg
    if isinstance(exc, BaseException):
        entry = f"{msg}\n" + "".join(traceback.format_exception(exc))
    log.error("%s", entry)
    add_error(entry)
    options = {"parent": parent} if parent is not None else {}
    messagebox.showerror(title or tr("dialog.error.title", "Error"), msg, **options)
    return msg
