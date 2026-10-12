"""Wizard writes to mod files: existing content, encoding and newlines survive."""

import json
import os
from types import SimpleNamespace

import pytest

import hoi4cm.core.logger as logmod
import hoi4cm.wizards._saves as saves
from hoi4cm.mod.context import ModContext

BOM = bytes((0xEF, 0xBB, 0xBF))
SID = "TAG_my_spirit"
SPIRIT_BLOCK = (
    "ideas = {\n\tcountry = {\n"
    f"\t\t{SID} = {{\n\t\t\tname = {SID}\n\t\t}}\n"
    "\t}\n}"
)
MID = "TAG_my_dynamic_modifier"
MOD_ENTRIES = [
    ("stability_factor", "TAG_stability_var", "stability_factor_tt"),
    ("political_power_gain", "TAG_power_var", ""),
]


@pytest.fixture
def mod():
    return ModContext()


@pytest.fixture
def error_buffer(monkeypatch):
    monkeypatch.setattr(logmod, "_error_callback", None)
    logmod.clear_errors()
    yield logmod.get_error_entries()
    logmod.clear_errors()


def _spirit_files(tmp_path, mod, ideas: bytes, loc: bytes):
    root = tmp_path / "mod"
    ideas_path = root / "common" / "ideas" / "existing.txt"
    loc_path = root / "localisation" / "english" / "existing_l_english.yml"
    ideas_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    ideas_path.write_bytes(ideas)
    loc_path.write_bytes(loc)
    mod.edit_ideas_file = str(ideas_path)
    mod.edit_loc_file = str(loc_path)
    return root, ideas_path, loc_path


def _save_spirit(mod, root, ideas_path, name="My National Spirit", desc="A desc."):
    return saves.save_spirit(
        mod,
        str(root),
        str(ideas_path),
        sid=SID,
        slot="country",
        ideas_block=SPIRIT_BLOCK,
        loc_name=name,
        loc_desc=desc,
    )


# ── national spirit ──────────────────────────────────────────────────


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_spirit_save_preserves_existing_blocks_and_localisation(tmp_path, mod, newline):
    ideas_before = (
        (
            "# Keep this header\n"
            "ideas = {\n\tcountry = {\n\t\tOTHER_spirit = {\n"
            '\t\t\tcustom_field = "keep } # literal"\n'
            "\t\t\tmodifier = { stability_factor = 0.2 }\n\t\t}\n"
            "\t}\n\thidden = {\n\t\tOTHER_hidden = { cost = 10 }\n\t}\n}\n"
            "# Keep this footer\n"
        )
        .replace("\n", newline)
        .encode("utf-8-sig")
    )
    loc_before = (
        (
            "l_english:\n # Keep this comment\n"
            ' OTHER_spirit:0 "Existing spirit"\n'
            ' OTHER_spirit_desc:0 "Existing description"\n'
        )
        .replace("\n", newline)
        .encode("utf-8-sig")
    )
    root, ideas_path, loc_path = _spirit_files(tmp_path, mod, ideas_before, loc_before)

    saved, warnings, errs = _save_spirit(
        mod, root, ideas_path, name='New "quoted" spirit'
    )

    ideas_after = ideas_path.read_bytes()
    loc_after = loc_path.read_bytes()
    slot_close = ("\t}" + newline + "\thidden").encode("utf-8")
    prefix, tail = ideas_before.split(slot_close, 1)
    assert ideas_after.startswith(prefix)
    assert ideas_after.endswith(slot_close + tail)
    assert ideas_after.count(f"{SID} = {{".encode()) == 1
    assert ideas_after.count(BOM) == 1
    expected_loc = (
        (f' {SID}: "New \\"quoted\\" spirit"\n {SID}_desc: "A desc."\n')
        .replace("\n", newline)
        .encode("utf-8")
    )
    assert loc_after == loc_before + expected_loc
    assert len(saved) == 2
    assert not warnings
    assert not errs

    saved, warnings, errs = _save_spirit(
        mod, root, ideas_path, name='New "quoted" spirit'
    )

    assert ideas_path.read_bytes() == ideas_after
    assert loc_path.read_bytes() == loc_after
    assert not saved
    assert any("already exists" in warning for warning in warnings)
    assert any("already present" in warning for warning in warnings)
    assert not errs


def test_spirit_new_files_are_created_under_the_mod_root(tmp_path, mod):
    root = tmp_path / "mod"
    ideas_path = root / "common" / "ideas" / f"{SID}.txt"

    saved, warnings, errs = _save_spirit(mod, root, ideas_path)

    assert ideas_path.read_text(encoding="utf-8") == SPIRIT_BLOCK
    loc_path = root / "localisation" / "english" / mod.loc_target.filename(SID)
    assert loc_path.read_bytes().startswith(BOM)
    assert f' {SID}: "My National Spirit"' in loc_path.read_text(encoding="utf-8-sig")
    assert len(saved) == 2
    assert not warnings
    assert not errs


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("Raw title", "Raw description"),
        ('A "quoted" name', 'A "quoted" description\\path\n§YColored§!'),
    ],
)
def test_spirit_localisation_values_round_trip(tmp_path, mod, title, description):
    loc_before = 'l_english:\n OTHER_spirit:0 "Existing spirit"\n'
    root, ideas_path, loc_path = _spirit_files(
        tmp_path,
        mod,
        b"ideas = {\n\tcountry = {\n\t}\n}\n",
        loc_before.encode("utf-8-sig"),
    )

    _save_spirit(mod, root, ideas_path, name=title, desc=description)

    localisation = loc_path.read_text(encoding="utf-8-sig")
    assert localisation.startswith(loc_before)
    values = {
        key: json.loads(value)
        for line in localisation.splitlines()[2:]
        for key, value in [line.strip().split(": ", 1)]
    }
    assert values == {SID: title, f"{SID}_desc": description}


def test_existing_spirit_id_is_skipped_without_changing_files(tmp_path, mod):
    ideas = (
        f"ideas = {{\n\tcountry = {{\n\t\t{SID} = {{\n"
        f"\t\t\tname = {SID}\n\t\t}}\n\t}}\n}}\n"
    ).encode()
    loc = (
        f'l_english:\n {SID}: "Existing spirit"\n {SID}_desc: "Existing description"\n'
    ).encode()
    root, ideas_path, loc_path = _spirit_files(tmp_path, mod, ideas, loc)

    saved, warnings, errs = _save_spirit(mod, root, ideas_path)

    assert ideas_path.read_bytes() == ideas
    assert loc_path.read_bytes() == loc
    assert not saved
    assert len(warnings) == 2
    assert not errs


@pytest.mark.parametrize("failed_target", ["ideas", "localisation"])
def test_spirit_save_reports_directory_failure(
    tmp_path, mod, monkeypatch, failed_target
):
    ideas_before = b"ideas = { country = { } }\n"
    loc_before = b"l_english:\n"
    root, ideas_path, loc_path = _spirit_files(tmp_path, mod, ideas_before, loc_before)
    failed_path = ideas_path if failed_target == "ideas" else loc_path
    makedirs = os.makedirs

    def fail_directory(path, **kwargs):
        if path == str(failed_path.parent):
            raise PermissionError("read-only directory")
        return makedirs(path, **kwargs)

    monkeypatch.setattr(saves.os, "makedirs", fail_directory)

    saved, _warnings, errs = _save_spirit(mod, root, ideas_path)

    assert len(errs) == 1
    assert "read-only directory" in errs[0]
    assert len(saved) == 1
    if failed_target == "ideas":
        assert ideas_path.read_bytes() == ideas_before
    else:
        assert loc_path.read_bytes() == loc_before


def test_spirit_save_reports_a_selected_file_that_is_gone(tmp_path, mod):
    root = tmp_path / "mod"
    mod.edit_ideas_file = str(root / "common" / "ideas" / "gone.txt")
    mod.edit_loc_file = str(root / "localisation" / "english" / "gone_l_english.yml")

    saved, _warnings, errs = _save_spirit(mod, root, mod.edit_ideas_file)

    assert not saved
    assert errs == [
        "Ideas: selected ideas file no longer exists",
        "Localisation: selected localisation file no longer exists",
    ]
    assert not os.path.exists(mod.edit_ideas_file)
    assert not os.path.exists(mod.edit_loc_file)


def test_spirit_appends_the_whole_block_when_the_slot_is_missing(tmp_path, mod):
    ideas_before = b"ideas = {\n\thidden = {\n\t}\n}\n"
    root, ideas_path, _loc_path = _spirit_files(
        tmp_path, mod, ideas_before, b"l_english:\n"
    )

    _saved, _warnings, errs = _save_spirit(mod, root, ideas_path)

    assert not errs
    assert ideas_path.read_bytes() == (
        ideas_before + b"\n\n" + SPIRIT_BLOCK.encode() + b"\n"
    )


def test_spirit_save_reports_unreadable_files_and_leaves_them(
    tmp_path, mod, monkeypatch
):
    ideas_before = b"\xff\xfeideas bytes\n"
    loc_before = b"\xff\xfeloc bytes\n"
    root, ideas_path, loc_path = _spirit_files(tmp_path, mod, ideas_before, loc_before)
    _unreadable(monkeypatch, ideas_path, loc_path)

    saved, _warnings, errs = _save_spirit(mod, root, ideas_path)

    assert not saved
    assert errs == [
        "Ideas: ideas file could not be read",
        "Localisation: localisation file could not be read",
    ]
    assert ideas_path.read_bytes() == ideas_before
    assert loc_path.read_bytes() == loc_before


def test_scripted_localisation_names_are_appended_once(tmp_path, mod):
    root, ideas_path, _loc_path = _spirit_files(
        tmp_path, mod, b"ideas = {\n\tcountry = {\n\t}\n}\n", b"l_english:\n"
    )
    sloc_path = root / "common" / "scripted_localisation" / "names.txt"
    sloc_path.parent.mkdir(parents=True)
    sloc_before = "defined_text = {\n\tname = GET_other\n}\n"
    sloc_path.write_text(sloc_before, encoding="utf-8")
    mod.edit_scripted_loc_file = str(sloc_path)

    _saved, _warnings, errs = _save_spirit(mod, root, ideas_path)

    after = sloc_path.read_text(encoding="utf-8")
    assert not errs
    assert after.startswith(sloc_before)
    assert after.count(f"name = GET_{SID}_name") == 1
    assert after.count(f"name = GET_{SID}_desc") == 1

    _save_spirit(mod, root, ideas_path)

    assert sloc_path.read_text(encoding="utf-8") == after


# ── events ───────────────────────────────────────────────────────────


def _event_files(tmp_path, mod, events: bytes, loc: bytes):
    root = tmp_path / "mod"
    event_path = root / "events" / "my_namespace.txt"
    loc_path = root / "localisation" / "english" / "my_namespace_l_english.yml"
    event_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    event_path.write_bytes(events)
    loc_path.write_bytes(loc)
    mod.edit_events_file = str(event_path)
    mod.edit_loc_file = str(loc_path)
    return root, event_path, loc_path


def _save_event(mod, root, event_path, eid="my_namespace.1"):
    return saves.save_events(
        mod,
        str(root),
        str(event_path),
        ns="my_namespace",
        events=[SimpleNamespace(eid=eid)],
        render_event=lambda ev: f"country_event = {{\n\tid = {ev.eid}\n}}",
        render_yml=lambda: (
            f'l_english:\n {eid}.t: "Title"\n {eid}.d: "Description"\n {eid}.a: "OK"\n'
        ),
    )


def test_existing_event_id_is_skipped_without_changing_files(tmp_path, mod):
    events = (
        b"add_namespace = my_namespace\n\ncountry_event = {\n\tid = my_namespace.1\n}\n"
    )
    loc = (
        b"l_english:\n"
        b' my_namespace.1.t: "Existing title"\n'
        b' my_namespace.1.d: "Existing description"\n'
        b' my_namespace.1.a: "Existing option"\n'
    )
    root, event_path, loc_path = _event_files(tmp_path, mod, events, loc)

    saved, warnings, errs = _save_event(mod, root, event_path)

    assert event_path.read_bytes() == events
    assert loc_path.read_bytes() == loc
    assert not saved
    assert any("my_namespace.1" in warning for warning in warnings)
    assert not errs


def test_event_append_keeps_existing_bytes_and_one_bom(tmp_path, mod):
    events = (
        "add_namespace = my_namespace\n\ncountry_event = {\n\tid = my_namespace.99\n}\n"
    ).encode("utf-8-sig")
    loc = b"l_english:\n"
    root, event_path, loc_path = _event_files(tmp_path, mod, events, loc)

    saved, _warnings, errs = _save_event(mod, root, event_path)

    after = event_path.read_bytes()
    assert after.startswith(events)
    assert after.count(BOM) == 1
    assert "id = my_namespace.1\n" in after.decode("utf-8-sig")
    loc_after = loc_path.read_bytes()
    assert loc_after.startswith(loc)
    assert b' my_namespace.1.t: "Title"' in loc_after
    assert len(saved) == 2
    assert not errs


def test_new_event_file_starts_with_its_namespace(tmp_path, mod):
    root = tmp_path / "mod"
    event_path = root / "events" / "my_namespace.txt"

    saved, warnings, errs = _save_event(mod, root, event_path)

    assert not warnings
    assert not errs
    assert len(saved) == 2
    assert event_path.read_text(encoding="utf-8").startswith(
        "add_namespace = my_namespace\n\n\ncountry_event = {\n\tid = my_namespace.1\n"
    )
    loc_path = (
        root
        / "localisation"
        / mod.loc_target.dirname()
        / mod.loc_target.filename("my_namespace")
    )
    loc = loc_path.read_bytes()
    assert loc.startswith(BOM)
    assert b"##########Events - my_namespace##########" in loc


def test_event_save_reports_a_selected_file_that_is_gone(tmp_path, mod):
    root = tmp_path / "mod"
    mod.edit_events_file = str(root / "events" / "gone.txt")
    mod.edit_loc_file = str(root / "localisation" / "english" / "gone_l_english.yml")

    saved, _warnings, errs = _save_event(mod, root, mod.edit_events_file)

    assert not saved
    assert errs == [
        "Events file: selected events file no longer exists",
        "Localisation: selected localisation file no longer exists",
    ]
    assert not os.path.exists(mod.edit_events_file)
    assert not os.path.exists(mod.edit_loc_file)


def test_event_render_failure_is_reported_and_leaves_the_file(tmp_path, mod):
    events = b"add_namespace = my_namespace\n"
    root, event_path, _loc_path = _event_files(tmp_path, mod, events, b"l_english:\n")

    def broken(_event):
        raise ValueError("cannot render")

    _saved, _warnings, errs = saves.save_events(
        mod,
        str(root),
        str(event_path),
        ns="my_namespace",
        events=[SimpleNamespace(eid="my_namespace.1")],
        render_event=broken,
        render_yml=lambda: "",
    )

    assert event_path.read_bytes() == events
    assert "Events file: cannot render" in errs


# ── dynamic modifiers ────────────────────────────────────────────────


def _save_dyn_mod(mod, root, icon=""):
    return saves.save_dyn_mod(
        mod,
        str(root),
        mid=MID,
        icon=icon,
        name="My Dynamic Modifier",
        desc="Scaling bonuses.",
        scope="country",
        enable="",
        mod_entries=MOD_ENTRIES,
        const_lines=[],
    )


def _dm_path(root):
    return root / "common" / "dynamic_modifiers" / f"{MID}.txt"


def _dm_loc_rel(mod):
    target = mod.loc_target
    return os.path.join("localisation", target.dirname(), target.filename(MID))


def _unreadable(monkeypatch, *paths):
    unread = {os.path.abspath(str(path)) for path in paths}
    original = saves.read_file_with_encoding

    def stub(path, *args, **kwargs):
        if os.path.abspath(str(path)) in unread:
            return None, None
        return original(path, *args, **kwargs)

    monkeypatch.setattr(saves, "read_file_with_encoding", stub)


def test_dyn_mod_save_creates_every_file(tmp_path, mod):
    results, errors = _save_dyn_mod(mod, tmp_path, icon="my_icon")

    assert not errors
    assert f"{MID} = {{" in _dm_path(tmp_path).read_text(encoding="utf-8")
    loc = (tmp_path / _dm_loc_rel(mod)).read_bytes()
    assert loc.startswith(BOM)
    assert f' {MID}: "My Dynamic Modifier"'.encode() in loc
    assert b' stability_factor_tt: "Stability Factor"' in loc
    gfx = (tmp_path / "interface" / "ideas.gfx").read_text(encoding="utf-8")
    assert "GFX_idea_my_icon" in gfx
    assert [action for _rel, action, _note in results] == [
        "created",
        "created",
        "created",
        "created",
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_dyn_mod_save_replaces_only_its_own_block(tmp_path, mod, newline):
    target = _dm_path(tmp_path)
    target.parent.mkdir(parents=True)
    before = (
        "# header\n"
        "OTHER_modifier = {\n\ticon = GFX_other\n}\n"
        f"{MID} = {{\n\ticon = GFX_old\n}}\n"
        "# footer\n"
    ).replace("\n", newline)
    target.write_bytes(before.encode("utf-8-sig"))

    results, errors = _save_dyn_mod(mod, tmp_path)

    after = target.read_bytes()
    assert not errors
    assert results[0][1] == "updated"
    assert after.count(BOM) == 1
    text = after.decode("utf-8-sig")
    head = f"# header{newline}OTHER_modifier = {{{newline}\ticon = GFX_other{newline}}}"
    assert text.startswith(head)
    assert text.endswith(f"}}{newline}# footer{newline}")
    assert "GFX_old" not in text
    assert text.count(f"{MID} = {{") == 1
    assert "\n" not in text.replace(newline, "")


def test_dyn_mod_save_skips_an_unreadable_modifier_file(
    tmp_path, mod, monkeypatch, error_buffer
):
    target = _dm_path(tmp_path)
    target.parent.mkdir(parents=True)
    original = b"\xff\xfeexisting modifier bytes\n"
    target.write_bytes(original)
    _unreadable(monkeypatch, target)

    results, errors = _save_dyn_mod(mod, tmp_path)

    rel = str(target.relative_to(tmp_path))
    assert target.read_bytes() == original
    assert errors == [f"Could not read existing file: {rel}"]
    assert any(rel in message for _, message in error_buffer)
    assert rel not in [result[0] for result in results]


@pytest.mark.parametrize("keys_exist_elsewhere", [False, True])
def test_dyn_mod_save_skips_an_unreadable_localisation_file(
    tmp_path, mod, monkeypatch, error_buffer, keys_exist_elsewhere
):
    loc_rel = _dm_loc_rel(mod)
    target = tmp_path / loc_rel
    target.parent.mkdir(parents=True)
    original = b"l_english:\n existing loc bytes\n"
    target.write_bytes(original)
    _unreadable(monkeypatch, target)
    if keys_exist_elsewhere:
        (target.parent / "existing_keys_l_english.yml").write_text(
            "l_english:\n"
            f' {MID}: "Name"\n'
            f' {MID}_desc: "Desc"\n'
            ' modifies_dynamic_modifier_tt: "Modifies $MODIFIER$"\n'
            ' stability_factor_tt: "Stability Factor"\n',
            encoding="utf-8-sig",
        )

    results, errors = _save_dyn_mod(mod, tmp_path)

    assert target.read_bytes() == original
    assert errors == [f"Could not read existing file: {loc_rel}"]
    assert loc_rel not in [result[0] for result in results]
    assert _dm_path(tmp_path).exists()


def test_dyn_mod_save_skips_an_unreadable_ideas_gfx(
    tmp_path, mod, monkeypatch, error_buffer
):
    gfx_rel = os.path.join("interface", "ideas.gfx")
    target = tmp_path / gfx_rel
    target.parent.mkdir(parents=True)
    original = b"spriteTypes = {\n existing gfx bytes\n}\n"
    target.write_bytes(original)
    _unreadable(monkeypatch, target)

    results, errors = _save_dyn_mod(mod, tmp_path, icon="my_icon")

    assert target.read_bytes() == original
    assert errors == [f"Could not read existing file: {gfx_rel}"]
    assert gfx_rel not in [result[0] for result in results]


def test_dyn_mod_save_appends_only_missing_localisation_keys(tmp_path, mod):
    loc_rel = _dm_loc_rel(mod)
    target = tmp_path / loc_rel
    target.parent.mkdir(parents=True)
    before = f'l_english:\n {MID}: "Kept name"\n'.encode("utf-8-sig")
    target.write_bytes(before)

    results, errors = _save_dyn_mod(mod, tmp_path)

    after = target.read_bytes()
    assert not errors
    assert after.startswith(before)
    assert after.count(BOM) == 1
    assert after.count(f" {MID}:".encode()) == 1
    assert f' {MID}_desc: "Scaling bonuses."'.encode() in after
    assert (loc_rel, "appended 3 new keys", "3 loc keys") in results

    results, _errors = _save_dyn_mod(mod, tmp_path)

    assert target.read_bytes() == after
    assert (loc_rel, "skipped", "all keys already exist") in results


# ── decisions ────────────────────────────────────────────────────────


def _save_decisions(mod, root, dec_path, cat_path):
    return saves.save_decisions(
        mod,
        str(root),
        ns="TAG",
        dec_path=str(dec_path),
        cat_path=str(cat_path),
        render_decisions=lambda: "TAG_category = {\n\tTAG_decision = {\n\t}\n}\n",
        render_categories=lambda: "TAG_category = {\n}\n",
        render_yml=lambda: 'l_english:\n TAG_decision: "Decision"\n',
        sloc_blocks=[],
    )


def test_decision_save_keeps_a_selected_files_encoding_and_newlines(tmp_path, mod):
    root = tmp_path / "mod"
    dec_path = root / "common" / "decisions" / "imported.txt"
    cat_path = root / "common" / "decisions" / "categories" / "imported.txt"
    loc_path = root / "localisation" / "english" / "imported_l_english.yml"
    for path in (dec_path, cat_path, loc_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    dec_path.write_bytes("OLD_category = {\r\n}\r\n".encode("utf-8-sig"))
    cat_path.write_bytes(b"OLD_category = {\r\n}\r\n")
    loc_before = 'l_english:\n TAG_other: "Other"\n'.encode("utf-8-sig")
    loc_path.write_bytes(loc_before)
    mod.edit_decisions_file = str(dec_path)
    mod.edit_decisions_cat_file = str(cat_path)
    mod.edit_loc_file = str(loc_path)

    saved, errs = _save_decisions(mod, root, dec_path, cat_path)

    assert not errs
    assert len(saved) == 3
    decisions = dec_path.read_bytes()
    assert decisions.count(BOM) == 1
    assert decisions.decode("utf-8-sig") == (
        "TAG_category = {\r\n\tTAG_decision = {\r\n\t}\r\n}\r\n"
    )
    assert cat_path.read_bytes() == b"TAG_category = {\r\n}\r\n"
    loc_after = loc_path.read_bytes()
    assert loc_after.startswith(loc_before)
    assert loc_after.count(BOM) == 1
    assert b' TAG_decision: "Decision"' in loc_after

    saved, errs = _save_decisions(mod, root, dec_path, cat_path)

    assert loc_path.read_bytes() == loc_after
    assert any("(+0 keys)" in entry for entry in saved)


def test_decision_save_creates_new_files(tmp_path, mod):
    root = tmp_path / "mod"
    dec_path = root / "common" / "decisions" / "TAG_decisions.txt"
    cat_path = root / "common" / "decisions" / "categories" / "TAG_categories.txt"

    saved, errs = _save_decisions(mod, root, dec_path, cat_path)

    assert not errs
    assert len(saved) == 3
    assert dec_path.read_bytes().startswith(b"TAG_category = {")
    assert cat_path.is_file()
    loc_path = (
        root
        / "localisation"
        / mod.loc_target.dirname()
        / mod.loc_target.filename("TAG_decisions")
    )
    assert loc_path.read_bytes().startswith(BOM)


def test_decision_save_reports_an_unreadable_selected_file(tmp_path, mod, monkeypatch):
    root = tmp_path / "mod"
    dec_path = root / "common" / "decisions" / "imported.txt"
    cat_path = root / "common" / "decisions" / "categories" / "TAG_categories.txt"
    dec_path.parent.mkdir(parents=True)
    original = b"\xff\xfeunreadable decisions\n"
    dec_path.write_bytes(original)
    mod.edit_decisions_file = str(dec_path)
    _unreadable(monkeypatch, dec_path)

    saved, errs = _save_decisions(mod, root, dec_path, cat_path)

    assert dec_path.read_bytes() == original
    assert "selected decisions file could not be read" in errs
    assert cat_path.is_file()
    assert len(saved) == 2
