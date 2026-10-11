"""Display-enabled insertion and save coverage for the Character Editor."""

import tkinter.messagebox as messagebox

from hoi4cm.mod import MOD
from hoi4cm.wizards import character as character_mod
from hoi4cm.wizards.character_codec import ScriptBlock, parse_character_script


def _block(block: ScriptBlock, key: str) -> ScriptBlock:
    return next(
        value
        for entry_key, value in block.entries
        if entry_key == key and isinstance(value, ScriptBlock)
    )


def test_new_character_inserts_role_trait_and_portrait_then_saves(
    tk_root, tmp_path, monkeypatch
):
    characters_dir = tmp_path / "common" / "characters"
    characters_dir.mkdir(parents=True)
    monkeypatch.setattr(MOD, "loaded", True)
    monkeypatch.setattr(MOD, "root", str(tmp_path))
    monkeypatch.setattr(messagebox, "showinfo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        character_mod,
        "open_universal_gfx_browser",
        lambda _parent, on_select, **_kwargs: on_select("GFX_portrait_aaa", ""),
    )

    wizard = character_mod.CharacterWizard(tk_root)
    wizard.open()
    wizard.tag_var.set("AAA")
    wizard.id_var.set("AAA_demo")
    wizard._new_file()
    assert wizard.editor.index("insert") != "1.0"

    wizard._choose_portrait()
    wizard.role_var.set("advisor")
    wizard._insert_role()
    wizard.trait_var.set("political_advisor")
    wizard._insert_trait()
    wizard._save()

    saved = characters_dir / "AAA.txt"
    document = parse_character_script(saved.read_text(encoding="utf-8"))
    characters = _block(document.root, "characters")
    character = _block(characters, "AAA_demo")
    advisor = _block(character, "advisor")
    traits = _block(advisor, "traits")
    assert (None, "political_advisor") in traits.entries
    portraits = _block(character, "portraits")
    civilian = _block(portraits, "civilian")
    assert ("large", "GFX_portrait_aaa") in civilian.entries


def test_opened_character_cursor_is_inside_its_body(tk_root, tmp_path, monkeypatch):
    source = "characters = {\n\tAAA_demo = {\n\t\tname = Demo\n\t}\n}\n"
    characters_dir = tmp_path / "common" / "characters"
    characters_dir.mkdir(parents=True)
    source_path = characters_dir / "AAA.txt"
    source_path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(MOD, "loaded", True)
    monkeypatch.setattr(MOD, "root", str(tmp_path))

    wizard = character_mod.CharacterWizard(tk_root)
    wizard.open()
    wizard._set_source(source, str(source_path))
    wizard._position_in_character_body("AAA_demo")

    assert wizard.editor.get("insert", "insert + 1 chars") == "}"
    assert wizard.body_indent == "\t\t"
