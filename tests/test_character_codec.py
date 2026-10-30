"""Round-trip tests for the ordered common/characters codec."""

from types import SimpleNamespace

import pytest

from hoi4cm.mod.index import ModIndex
from hoi4cm.wizards.character_codec import (
    new_character_script,
    parse_character_script,
)


def test_import_export_preserves_unknown_fields_and_interleaved_duplicates():
    source = """
characters = {
    AAA_demo = {
        name = "Ada Example"
        country_leader = { ideology = democratic traits = { careful } }
        custom_mod_field = { nested = "kept value" }
        1936 = { unknown_numeric_key = yes }
        custom_field = "="
        custom_rule = { has_start_date >= 1936.1.1 }
        compact_rule = { date>=1936.1.1 command_power<75 }
        portraits = { civilian = { large = GFX_ada } }
        advisor = { idea_token = AAA_ada slot = political_advisor }
        country_leader = { ideology = neutrality traits = { reformer } }
        portraits = { army = { large = GFX_ada_army } }
    }
}
"""

    first = parse_character_script(source)
    encoded = first.to_text()
    second = parse_character_script(encoded)

    assert second == first
    assert first.character_ids() == ["AAA_demo"]
    assert encoded.index("country_leader =") < encoded.index("custom_mod_field")
    assert encoded.index("custom_mod_field") < encoded.index("portraits =")
    assert encoded.count("country_leader =") == 2
    assert encoded.count("portraits =") == 2
    assert 'nested = "kept value"' in encoded
    assert "slot = political_advisor" in encoded
    assert "1936 = {" in encoded
    assert 'custom_field = "="' in encoded
    assert "has_start_date >= 1936.1.1" in encoded
    assert "date >= 1936.1.1" in encoded
    assert "command_power < 75" in encoded
    assert "1936.1.1" in encoded


def test_round_trip_keeps_repeated_bare_trait_values():
    source = "characters = { X = { advisor = { traits = { trait_a trait_b } } } }"
    encoded = parse_character_script(source).to_text()

    assert "traits = {\n\t\t\t\ttrait_a\n\t\t\t\ttrait_b\n\t\t\t}" in encoded
    assert parse_character_script(encoded) == parse_character_script(source)


@pytest.mark.parametrize("value", ["a>b", "a<b", "a!b"])
def test_round_trip_quotes_operator_characters_in_quoted_scalars(value):
    source = f'characters = {{ X = {{ name = "{value}" }} }}'

    document = parse_character_script(source)
    encoded = document.to_text()

    assert f'name = "{value}"' in encoded
    assert parse_character_script(encoded) == document


def test_new_character_template_validates_identifiers_and_round_trips():
    generated = new_character_script("AAA", "AAA_example")

    parsed = parse_character_script(generated)
    reloaded = parse_character_script(parsed.to_text())
    assert parsed.character_ids() == ["AAA_example"]
    assert reloaded == parsed
    assert 'name = ""' in parsed.to_text()
    assert "AAA_example = {" in generated
    with pytest.raises(ValueError, match="script identifiers"):
        new_character_script("A A", "AAA_example")


def test_saving_imported_character_keeps_original_encoding_across_saves(
    tmp_path, monkeypatch
):
    from hoi4cm.wizards import character as character_mod

    characters_dir = tmp_path / "common" / "characters"
    characters_dir.mkdir(parents=True)

    class _Editor:
        def get(self, *_args):
            return 'characters = { X = { name = "André" } }'

    class _Writer:
        def __init__(self):
            self.encodings = []

        def write_text(self, _path, _source, *, encoding):
            self.encodings.append(encoding)

    wizard = object.__new__(character_mod.CharacterWizard)
    wizard.editor = _Editor()
    wizard.current_path = str(characters_dir / "characters.txt")
    wizard.current_encoding = "latin-1"
    wizard.mod_root = str(tmp_path)
    wizard.win = None
    wizard.app = SimpleNamespace(index=ModIndex(), note_mod_file_written=lambda _: None)
    writer = _Writer()
    monkeypatch.setattr(
        character_mod,
        "notifying_workspace_files",
        lambda _index, _root, _on_written: writer,
    )
    monkeypatch.setattr(character_mod.messagebox, "showinfo", lambda *_a, **_kw: None)

    wizard._save()
    wizard._save()

    assert writer.encodings == ["latin-1", "latin-1"]


@pytest.mark.parametrize(
    ("original", "edited"),
    [
        (
            "# Keep this header comment\n"
            '# Disabled legacy = { name = "Not active" }\n'
            'characters = { X = { name = "Ada" } }\n',
            None,
        ),
        (
            "# Keep this header comment\n"
            '# Disabled legacy = { name = "Not active" }\n'
            'characters = { X = { name = "Ada" } }\n',
            "# Keep this header comment\n"
            '# Disabled legacy = { name = "Not active" }\n'
            'characters = { X = { name = "Ada Lovelace" } }\n',
        ),
    ],
    ids=["no-change", "edited"],
)
def test_character_save_preserves_comments_and_disabled_script(
    tmp_path, monkeypatch, original, edited
):
    from hoi4cm.wizards import character as character_mod

    characters_dir = tmp_path / "common" / "characters"
    characters_dir.mkdir(parents=True)
    target = characters_dir / "characters.txt"
    expected = original if edited is None else edited

    class _Editor:
        def get(self, *_args):
            return expected

    wizard = object.__new__(character_mod.CharacterWizard)
    wizard.editor = _Editor()
    wizard.current_path = str(target)
    wizard.current_encoding = "utf-8"
    wizard.mod_root = str(tmp_path)
    wizard.win = None
    wizard.app = SimpleNamespace(index=ModIndex(), note_mod_file_written=lambda _: None)
    monkeypatch.setattr(character_mod.messagebox, "showinfo", lambda *_a, **_kw: None)

    wizard._save()

    assert target.read_text(encoding="utf-8") == expected


def test_character_target_rejects_a_directory_symlink_outside_the_mod(
    tmp_path, monkeypatch
):
    import shutil

    from hoi4cm.wizards import character as character_mod

    characters_dir = tmp_path / "common" / "characters"
    characters_dir.parent.mkdir(parents=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    try:
        characters_dir.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    class _Value:
        def get(self):
            return "AAA"

    wizard = object.__new__(character_mod.CharacterWizard)
    wizard.mod_root = str(tmp_path)
    wizard.tag_var = _Value()
    wizard.win = None
    errors = []
    monkeypatch.setattr(
        character_mod.messagebox,
        "showerror",
        lambda _title, message, **_kwargs: errors.append(message),
    )

    try:
        assert wizard._new_target() is None
        assert errors

        writer_calls = []

        class _Writer:
            def write_text(self, *_args, **_kwargs):
                writer_calls.append(True)

        monkeypatch.setattr(
            character_mod,
            "notifying_workspace_files",
            lambda *_args: _Writer(),
        )
        monkeypatch.setattr(character_mod, "report_error", lambda *_a, **_kw: None)

        class _Editor:
            def get(self, *_args):
                return "characters = { AAA_demo = { name = Demo } }"

        wizard.editor = _Editor()
        wizard.current_path = str(characters_dir / "AAA.txt")
        wizard.current_encoding = "utf-8"
        wizard._save()

        assert not writer_calls
        assert not (outside / "AAA.txt").exists()
    finally:
        shutil.rmtree(outside, ignore_errors=True)


class _FakeEditor:
    """Minimal headless stand-in for the wizard's tk.Text editor."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._insert_pos = "1.0"

    def index(self, mark: str) -> str:
        assert mark == "insert"
        return self._insert_pos

    def insert(self, _mark: str, text: str) -> None:
        row, column = (int(part) for part in self._insert_pos.split("."))
        lines = self._source.split("\n")
        lines[row - 1] = lines[row - 1][:column] + text + lines[row - 1][column:]
        self._source = "\n".join(lines)

    def mark_set(self, mark: str, index: str) -> None:
        if mark == "insert":
            self._insert_pos = index

    def focus_set(self) -> None:
        return None

    def text(self) -> str:
        return self._source


class _FakeVar:
    """Minimal headless stand-in for tk.StringVar."""

    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


def test_field_marshal_role_offered_and_inserted_as_valid_block():
    from hoi4cm.wizards import character as character_mod

    assert "field_marshal" in character_mod.ROLE_NAMES

    wizard = object.__new__(character_mod.CharacterWizard)
    editor = _FakeEditor('characters = {\n\tAAA_ada = {\n\t\tname = "Ada"\n\t}\n}\n')
    wizard.editor = editor
    wizard.body_indent = "\t\t"
    wizard.character_close_indent = "\t"
    wizard.role_var = _FakeVar("field_marshal")
    # _position_in_character_body leaves the caret on the closing brace itself.
    editor.mark_set("insert", "4.1")

    wizard._insert_role()

    inserted = editor.text()
    assert inserted == (
        'characters = {\n\tAAA_ada = {\n\t\tname = "Ada"\n\t\n'
        "\t\tfield_marshal = {\n\t\t\t\n\t\t}\n\t}\n}\n"
    )
    document = parse_character_script(inserted)
    assert document == parse_character_script(document.to_text())
    assert document.character_ids() == ["AAA_ada"]
    # Caret lands on the blank body line of the new block, column = len(role_indent).
    assert editor.index("insert") == "6.3"


def test_existing_field_marshal_block_round_trips_with_skills_and_traits():
    source = """
characters = {
    AAA_ada = {
        name = "Ada"
        field_marshal = {
            skill = 3
            attack_skill = 4
            defense_skill = 2
            planning_skill = 3
            logistics_skill = 2
            traits = { old_guard organizer }
        }
        corps_commander = { skill = 2 traits = { trait_cavalry_leader } }
        field_marshal = { skill = 1 custom_field = kept }
    }
}
"""

    document = parse_character_script(source)
    encoded = document.to_text()

    assert parse_character_script(encoded) == document
    assert encoded.count("field_marshal = {") == 2
    for kept in ("attack_skill = 4", "logistics_skill = 2", "custom_field = kept"):
        assert kept in encoded
    assert "old_guard" in encoded
    assert "organizer" in encoded
    assert encoded.index("field_marshal") < encoded.index("corps_commander")
    assert encoded.index("corps_commander") < encoded.rindex("field_marshal")


@pytest.mark.parametrize(
    "source",
    ["characters = { X = {", "characters = }", "x = { } }"],
)
def test_malformed_script_is_rejected(source):
    with pytest.raises(ValueError):
        parse_character_script(source)
