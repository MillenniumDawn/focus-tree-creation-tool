"""Character authoring dialog backed by the ordered character-script codec."""

from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from hoi4cm.core import read_file_with_encoding, sanitize_component, tr
from hoi4cm.mod import MOD, notifying_workspace_files
from hoi4cm.script.syntax import match_brace
from hoi4cm.ui import BG_DARK, BG_PANEL, BLUE, BORDER_G, TEXT, TEXT_DIM, report_error
from hoi4cm.ui.gfx_browser import open_universal_gfx_browser
from hoi4cm.wizards.character_codec import new_character_script, parse_character_script

ROLE_NAMES = (
    "country_leader",
    "advisor",
    "corps_commander",
    "navy_leader",
    "operative",
    "scientist",
)


class CharacterWizard:
    """Own the dialog state and keep widget callbacks small and isolated."""

    def __init__(self, app: tk.Tk) -> None:
        self.app = app
        self.mod_root = MOD.root or ""
        self.win: Any = None
        self.editor: Any = None
        self.tag_var: Any = None
        self.id_var: Any = None
        self.trait_var: Any = None
        self.role_var: Any = None
        self.current_path: str | None = None
        self.current_encoding = "utf-8"
        self.body_indent = "\t\t"
        self.character_close_indent = "\t"

    def open(self) -> None:
        if not MOD.loaded or not self.mod_root:
            messagebox.showinfo(
                tr("wizard.character.title", "Character Editor"),
                tr(
                    "wizard.character.load_mod", "Load a mod before editing characters."
                ),
                parent=self.app,
            )
            return
        self.win = tk.Toplevel(self.app)
        self.win.title(tr("wizard.character.title", "Character Editor"))
        self.win.configure(bg=BG_DARK)
        self.win.geometry("900x680")
        self.win.minsize(720, 520)
        self.win.transient(self.app)
        self._build_ui()

    def _build_ui(self) -> None:
        self.tag_var = tk.StringVar(master=self.win, value="")
        self.id_var = tk.StringVar(master=self.win, value="")
        self.trait_var = tk.StringVar(master=self.win, value="")
        header = tk.Frame(
            self.win, bg=BG_PANEL, highlightbackground=BORDER_G, highlightthickness=1
        )
        header.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(
            header,
            text=tr("wizard.character.country", "Country tag"),
            bg=BG_PANEL,
            fg=TEXT,
        ).grid(row=0, column=0, padx=(10, 4), pady=8, sticky="w")
        tk.Entry(header, textvariable=self.tag_var, width=12).grid(
            row=0, column=1, padx=4, pady=8
        )
        tk.Label(
            header, text=tr("wizard.character.id", "Character ID"), bg=BG_PANEL, fg=TEXT
        ).grid(row=0, column=2, padx=(12, 4), pady=8, sticky="w")
        ttk.Combobox(
            header,
            textvariable=self.id_var,
            values=tuple(getattr(MOD, "character_ids", ())),
            width=32,
        ).grid(row=0, column=3, padx=4, pady=8, sticky="ew")
        header.columnconfigure(3, weight=1)
        tk.Label(
            self.win,
            text=tr(
                "wizard.character.hint",
                "Insertions go at the cursor. Place it in the character block "
                "for roles or portraits, or a role block for traits. Unknown "
                "fields and duplicate blocks are retained.",
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            anchor="w",
            justify="left",
            wraplength=850,
        ).pack(fill="x", padx=12, pady=(2, 6))
        editor_frame = tk.Frame(self.win, bg=BG_PANEL)
        editor_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.editor = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            bg="#171b22",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("TkFixedFont", 10),
        )
        yscroll = ttk.Scrollbar(
            editor_frame, orient="vertical", command=self.editor.yview
        )
        xscroll = ttk.Scrollbar(
            editor_frame, orient="horizontal", command=self.editor.xview
        )
        self.editor.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.editor.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)
        self._build_controls()
        self._set_source("characters = {\n}\n")

    def _build_controls(self) -> None:
        controls = tk.Frame(self.win, bg=BG_DARK)
        controls.pack(fill="x", padx=10, pady=(5, 10))
        tk.Button(
            controls,
            text=tr("wizard.character.open", "Open file"),
            command=self._open_file,
        ).pack(side="left", padx=3)
        tk.Button(
            controls, text=tr("wizard.character.new", "New"), command=self._new_file
        ).pack(side="left", padx=3)
        self.role_var = tk.StringVar(master=self.win, value=ROLE_NAMES[0])
        ttk.Combobox(
            controls,
            textvariable=self.role_var,
            values=ROLE_NAMES,
            state="readonly",
            width=19,
        ).pack(side="left", padx=(12, 3))
        tk.Button(
            controls,
            text=tr("wizard.character.add_role", "Insert role block"),
            command=self._insert_role,
        ).pack(side="left", padx=3)
        tk.Entry(controls, textvariable=self.trait_var, width=18).pack(
            side="left", padx=(12, 3)
        )
        tk.Button(
            controls,
            text=tr("wizard.character.add_trait", "Insert trait"),
            command=self._insert_trait,
        ).pack(side="left", padx=3)
        tk.Button(
            controls,
            text=tr("wizard.character.portrait", "Portrait"),
            command=self._choose_portrait,
        ).pack(side="left", padx=3)
        tk.Button(
            controls,
            text=tr("wizard.character.save", "Save"),
            command=self._save,
            bg=BLUE,
            fg="white",
        ).pack(side="right", padx=3)

    def _set_source(
        self, source: str, path: str | None = None, character_id: str | None = None
    ) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", source)
        self.current_path = path
        if path is None:
            self.current_encoding = "utf-8"
        if character_id:
            self._position_in_character_body(character_id)

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.win,
            title=tr("wizard.character.open", "Open character file"),
            initialdir=os.path.join(self.mod_root, "common", "characters"),
            filetypes=(("HOI4 script", "*.txt"), ("All files", "*")),
        )
        if not path:
            return
        expected = os.path.realpath(os.path.join(self.mod_root, "common", "characters"))
        resolved = os.path.realpath(path)
        if not self._inside_directory(expected, resolved):
            messagebox.showerror(
                tr("wizard.character.title", "Character Editor"),
                tr(
                    "wizard.character.invalid_file",
                    "Choose a file inside common/characters.",
                ),
                parent=self.win,
            )
            return
        try:
            source, encoding = read_file_with_encoding(resolved)
            if source is None:
                raise OSError("Character file could not be read")
            document = parse_character_script(source)
        except (OSError, ValueError) as exc:
            report_error(
                tr("wizard.character.read_error", "Could not read character file."),
                exc,
                parent=self.win,
            )
            return
        self.current_encoding = encoding or "utf-8"
        self._set_source(source, resolved)
        ids = document.character_ids()
        if ids:
            self.id_var.set(ids[0])
            self.tag_var.set(os.path.splitext(os.path.basename(resolved))[0].upper())
            self._position_in_character_body(ids[0])

    def _position_in_character_body(self, character_id: str) -> None:
        source = self.editor.get("1.0", "end-1c")
        match = re.search(rf"(?m)^[\t ]*{re.escape(character_id)}\s*=\s*\{{", source)
        if match is None:
            return
        open_index = source.find("{", match.start(), match.end())
        close_index = match_brace(source, open_index)
        if close_index >= len(source):
            return
        opening_indent = re.match(r"[\t ]*", match.group())
        self.body_indent = (opening_indent.group() if opening_indent else "") + "\t"
        closing_line = source.rfind("\n", 0, close_index) + 1
        close_prefix = source[closing_line:close_index]
        self.character_close_indent = close_prefix if not close_prefix.strip() else ""
        self.editor.mark_set("insert", f"1.0 + {close_index} chars")
        self.editor.see("insert")

    @staticmethod
    def _inside_directory(parent: str, path: str) -> bool:
        try:
            return os.path.commonpath((parent, path)) == parent
        except ValueError:
            return False

    def _new_file(self) -> None:
        raw_tag = self.tag_var.get().strip().upper()
        raw_character_id = self.id_var.get().strip()
        if not raw_tag or not raw_character_id:
            messagebox.showerror(
                tr("wizard.character.title", "Character Editor"),
                tr(
                    "wizard.character.required",
                    "Enter a country tag and character ID first.",
                ),
                parent=self.win,
            )
            return
        tag = sanitize_component(raw_tag)
        character_id = sanitize_component(raw_character_id)
        try:
            self._set_source(
                new_character_script(tag, character_id), character_id=character_id
            )
        except ValueError as exc:
            messagebox.showerror(
                tr("wizard.character.title", "Character Editor"),
                str(exc),
                parent=self.win,
            )

    def _insert_role(self) -> None:
        role = self.role_var.get()
        if role not in ROLE_NAMES:
            return
        row = int(self.editor.index("insert").split(".")[0])
        role_indent = self.body_indent + "\t"
        snippet = (
            f"\n{self.body_indent}{role} = {{\n{role_indent}\n"
            f"{self.body_indent}}}\n{self.character_close_indent}"
        )
        self.editor.insert("insert", snippet)
        self.editor.mark_set("insert", f"{row + 2}.{len(role_indent)}")
        self.editor.focus_set()

    def _insert_trait(self) -> None:
        trait = self.trait_var.get().strip()
        if not trait or any(char.isspace() or char in '{}=#"' for char in trait):
            messagebox.showerror(
                tr("wizard.character.title", "Character Editor"),
                tr(
                    "wizard.character.trait_invalid", "Enter a single trait identifier."
                ),
                parent=self.win,
            )
            return
        row, column = map(int, self.editor.index("insert").split("."))
        line_prefix = self.editor.get(f"{row}.0", f"{row}.{column}")
        self.editor.insert("insert", f"traits = {{ {trait} }}\n{line_prefix}")
        self.trait_var.set("")
        self.editor.focus_set()

    def _choose_portrait(self) -> None:
        def selected(key: str, _path: str) -> None:
            self.editor.insert(
                "insert",
                f"\n{self.body_indent}portraits = {{\n"
                f"{self.body_indent}\tcivilian = {{ large = {key} small = {key} }}\n"
                f"{self.body_indent}}}\n{self.character_close_indent}",
            )
            self.editor.focus_set()

        open_universal_gfx_browser(
            self.win,
            selected,
            title=tr("wizard.character.portrait", "Select portrait"),
            gfx_hints=["interface"],
            mod=MOD,
        )

    def _save(self) -> None:
        source = self.editor.get("1.0", "end-1c")
        try:
            document = parse_character_script(source)
            if not document.character_ids():
                raise ValueError(
                    "The file must contain at least one character definition."
                )
            source = document.to_text()
        except ValueError as exc:
            messagebox.showerror(
                tr("wizard.character.invalid_script", "Invalid character script"),
                str(exc),
                parent=self.win,
            )
            return
        target = self.current_path or self._new_target()
        if target is None:
            return
        try:
            notifying_workspace_files(MOD, self.mod_root).write_text(
                target, source, encoding=self.current_encoding
            )
        except (OSError, ValueError) as exc:
            report_error(
                tr("wizard.character.write_error", "Could not save character file."),
                exc,
                parent=self.win,
            )
            return
        self.current_path = target
        messagebox.showinfo(
            tr("wizard.character.title", "Character Editor"),
            tr("wizard.character.saved", "Character file saved."),
            parent=self.win,
        )

    def _new_target(self) -> str | None:
        raw_tag = self.tag_var.get().strip().upper()
        if not raw_tag:
            messagebox.showerror(
                tr("wizard.character.title", "Character Editor"),
                tr(
                    "wizard.character.required",
                    "Enter a country tag and character ID first.",
                ),
                parent=self.win,
            )
            return None
        tag = sanitize_component(raw_tag)
        target = os.path.join(self.mod_root, "common", "characters", f"{tag}.txt")
        if os.path.exists(target) and not messagebox.askyesno(
            tr("wizard.character.title", "Character Editor"),
            tr(
                "wizard.character.replace_existing",
                "That file already exists. Replace it?",
            ),
            parent=self.win,
        ):
            return None
        return target


def open_character_wizard(app: tk.Tk) -> None:
    """Open the character authoring wizard."""
    CharacterWizard(app).open()
