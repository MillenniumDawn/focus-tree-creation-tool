"""Exercise the frozen executable's Tcl/Tk runtime without opening the editor."""

import tkinter as tk
from tkinter import ttk


def check_tk_startup() -> None:
    """Fail on missing Tcl/Tk scripts, native libraries, or ttk theme resources."""
    root = tk.Tk()
    root.withdraw()
    try:
        ttk.Label(root, text="Startup check").pack()
        root.update_idletasks()
        root.update()
    finally:
        root.destroy()
