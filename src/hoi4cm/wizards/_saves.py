# ruff: noqa: E501
"""Wizard writes to mod files, with no Tk.

Each wizard's dialog collects its form state and resolves the target paths,
then hands plain values to one function here. Existing files keep their bytes:
content is appended, or one block is replaced, in the file's own encoding and
newline style.
"""

import json
import os
import re

from hoi4cm.core import (
    add_error,
    append_scripted_loc,
    convert_newlines,
    get_logger,
    newline_style,
    read_file_with_encoding,
)
from hoi4cm.mod import append_sprite_types, find_loc_files, notifying_workspace_files
from hoi4cm.script.syntax import match_brace
from hoi4cm.wizards._generators import build_event_scripted_loc_blocks

# Accepts both the modern `key: "value"` form and the legacy `key:0 "value"` form.
_LOC_KEY = re.compile(r'\s+(\S+?)(?::\d+)?\s*[=:]?\s*"')

_READ_MISSING = "missing"
_READ_FAILED = "read-failed"
_READ_CONTENT = "content"


def _read_existing_file_with_encoding(path):
    if not os.path.exists(path):
        return _READ_MISSING, None, None
    try:
        content, encoding = read_file_with_encoding(path)
    except OSError, UnicodeDecodeError, ValueError:
        return _READ_FAILED, None, None
    if content is None or encoding is None:
        return _READ_FAILED, None, None
    return _READ_CONTENT, content, encoding


def save_spirit(
    mod, mod_root, ideas_path, *, sid, slot, ideas_block, loc_name, loc_desc
):
    """Add one national spirit to the ideas and localisation files.

    Returns ``(saved, warnings, errs)`` for ``format_save_summary``.
    """
    saved = []
    errs = []
    warnings = []
    wf = notifying_workspace_files(mod, mod_root)

    # ── SAFE APPEND to ideas file ─────────────────────────────────────
    try:
        os.makedirs(os.path.dirname(ideas_path), exist_ok=True)
        selected_ideas = bool(mod.edit_ideas_file)
        file_exists = os.path.isfile(ideas_path)
        if selected_ideas and not file_exists:
            raise OSError("selected ideas file no longer exists")
        ideas_encoding = "utf-8"
        if file_exists:
            existing, ideas_encoding = read_file_with_encoding(ideas_path)
            if existing is None or ideas_encoding is None:
                raise OSError("ideas file could not be read")
            # Check if spirit ID already defined
            if re.search(r"\b" + re.escape(sid) + r"\s*=\s*\{", existing):
                warnings.append(
                    f"Spirit '{sid}' already exists in file — skipped (edit the file manually to update it)."
                )
            else:
                # Extract the spirit's own block from ideas_block
                # ideas_block = "ideas { <slot> { <sid> = { ... } } }"
                m_spirit = re.search(r"\b" + re.escape(sid) + r"\s*=\s*\{", ideas_block)
                if m_spirit:
                    spirit_start = m_spirit.start()
                    brace_start = ideas_block.index("{", spirit_start)
                    close_pos = match_brace(ideas_block, brace_start)
                    spirit_end = (
                        close_pos + 1 if close_pos < len(ideas_block) else brace_start
                    )
                    spirit_block = "\t\t" + ideas_block[
                        spirit_start:spirit_end
                    ].replace("\n", "\n\t\t")
                else:
                    spirit_block = None

                if spirit_block:
                    # Find the slot section (e.g. "country = {") and insert before its closing }
                    slot_pat = re.compile(r"\b" + re.escape(slot) + r"\s*=\s*\{")
                    sm = slot_pat.search(existing)
                    if sm:
                        si2 = existing.index("{", sm.start())
                        close_pos = match_brace(existing, si2)
                        if close_pos >= len(existing):
                            close_pos = si2
                        inserted = convert_newlines(
                            "\n\n" + spirit_block + "\n\t",
                            newline_style(existing),
                        )
                        new_existing = (
                            existing[:close_pos] + inserted + existing[close_pos:]
                        )
                    else:
                        # Slot section not found — append full block at end
                        inserted = convert_newlines(
                            "\n\n" + ideas_block + "\n",
                            newline_style(existing),
                        )
                        new_existing = existing + inserted
                else:
                    inserted = convert_newlines(
                        "\n\n" + ideas_block + "\n", newline_style(existing)
                    )
                    new_existing = existing + inserted

                wf.write_text(ideas_path, new_existing, encoding=ideas_encoding)
                rel = os.path.relpath(ideas_path, mod_root)
                saved.append(rel + "  (spirit appended into existing file)")
        else:
            # New file — write as-is
            wf.write_text(ideas_path, ideas_block, encoding="utf-8")
            rel = os.path.relpath(ideas_path, mod_root)
            saved.append(rel + "  (new file created)")

    except (OSError, ValueError, RuntimeError, UnicodeDecodeError) as exc:
        errs.append("Ideas: " + str(exc))

    # ── SAFE APPEND to localisation ───────────────────────────────────
    selected_loc = bool(mod.edit_loc_file)
    if selected_loc:
        loc_path = mod.edit_loc_file
    else:
        loc_target = mod.loc_target
        loc_path = os.path.join(
            mod_root,
            "localisation",
            loc_target.dirname(),
            loc_target.filename(sid),
        )
    try:
        os.makedirs(os.path.dirname(loc_path), exist_ok=True)
        new_entries = {sid: loc_name, f"{sid}_desc": loc_desc}
        existing_keys = set()
        loc_encoding = "utf-8-sig"
        loc_exists = os.path.isfile(loc_path)
        if selected_loc and not loc_exists:
            raise OSError("selected localisation file no longer exists")
        if loc_exists:
            loc_text, loc_encoding = read_file_with_encoding(loc_path)
            if loc_text is None or loc_encoding is None:
                raise OSError("localisation file could not be read")
            for line in loc_text.splitlines():
                m = _LOC_KEY.match(line)
                if m:
                    existing_keys.add(m.group(1))

        to_add = {k: v for k, v in new_entries.items() if k not in existing_keys}
        if to_add:
            if not loc_exists:
                wf.write_text(
                    loc_path,
                    mod.loc_target.header() + "\n",
                    encoding=loc_encoding,
                )
            loc_body = "".join(
                f" {k}: {json.dumps(v, ensure_ascii=False)}\n"
                for k, v in to_add.items()
            )
            wf.append_text(loc_path, loc_body, encoding=loc_encoding)
            rel = os.path.relpath(loc_path, mod_root)
            saved.append(rel + f"  (+{len(to_add)} keys)")
        else:
            warnings.append("Localisation keys already present — skipped.")
    except (OSError, ValueError, RuntimeError, UnicodeDecodeError) as exc:
        errs.append("Localisation: " + str(exc))

    # ── SCRIPTED LOC ─────────────────────────────────────────────────
    if mod.edit_scripted_loc_file:
        sloc_blocks = []
        if sid:
            sloc_blocks.append({"name": f"GET_{sid}_name", "texts": [], "default": sid})
            if loc_desc:
                sloc_blocks.append(
                    {
                        "name": f"GET_{sid}_desc",
                        "texts": [],
                        "default": f"{sid}_desc",
                    }
                )
        append_scripted_loc(
            mod.edit_scripted_loc_file,
            sloc_blocks,
            saved,
            errs,
            mod_root,
            require_existing=True,
        )

    return saved, warnings, errs


def save_events(mod, mod_root, ev_file, *, ns, events, render_event, render_yml):
    """Append events to the events and localisation files.

    ``events`` need an ``eid``. The two renderers run inside the error
    handling, so a failed render is reported instead of raised. Returns
    ``(saved, warnings, errs)`` for ``format_save_summary``.
    """
    saved = []
    errs = []
    warnings = []

    selected_event = bool(mod.edit_events_file)
    selected_loc = bool(mod.edit_loc_file)
    if selected_loc:
        loc_file = mod.edit_loc_file
    else:
        loc_target = mod.loc_target
        loc_file = os.path.join(
            mod_root,
            "localisation",
            loc_target.dirname(),
            loc_target.filename(ns),
        )
    os.makedirs(os.path.dirname(ev_file), exist_ok=True)
    os.makedirs(os.path.dirname(loc_file), exist_ok=True)
    wf = notifying_workspace_files(mod, mod_root)

    # ── EVENTS: safe append — never touch existing content ────────────
    try:
        existing_ids = set()
        file_exists = os.path.isfile(ev_file)
        if selected_event and not file_exists:
            raise OSError("selected events file no longer exists")
        event_encoding = "utf-8"
        if file_exists:
            raw, event_encoding = read_file_with_encoding(ev_file)
            if raw is None or event_encoding is None:
                raise OSError("events file could not be read")
            # Collect every id = X already in the file
            for m in re.finditer(r"\bid\s*=\s*(\S+)", raw):
                existing_ids.add(m.group(1).strip())

        to_append = [ev for ev in events if ev.eid not in existing_ids]
        skipped = [ev.eid for ev in events if ev.eid in existing_ids]
        if skipped:
            warnings.append("Already in file (skipped): " + ", ".join(skipped))

        if to_append:
            lines = []
            if not file_exists:
                # Brand-new file — write namespace header first
                lines.append(f"add_namespace = {ns}")
                lines.append("")
            else:
                lines.append("")
                lines.append(
                    "# ── Appended by HOI4 Content Maker ─────────────────────────────────"
                )
            for ev in to_append:
                lines.append("")
                lines.append(render_event(ev))

            ev_content = "\n".join(lines) + "\n"
            if file_exists:
                wf.append_text(ev_file, ev_content, encoding=event_encoding)
            else:
                wf.write_text(ev_file, ev_content, encoding=event_encoding)
            rel = os.path.relpath(ev_file, mod_root)
            saved.append(
                f"{rel}  (+{len(to_append)} event{'s' if len(to_append) != 1 else ''})"
            )
        else:
            warnings.append(
                "No new events to append — all IDs already present in file."
            )

    except (OSError, ValueError, RuntimeError, UnicodeDecodeError) as exc:
        errs.append("Events file: " + str(exc))

    # ── LOCALISATION: safe append — skip keys already present ─────────
    try:
        yml_new_lines = []
        loc_header = mod.loc_target.header()
        for line in render_yml().splitlines():
            if not line.strip() or line.strip() == loc_header:
                continue
            yml_new_lines.append(line)

        existing_yml_keys = set()
        yml_exists = os.path.isfile(loc_file)
        if selected_loc and not yml_exists:
            raise OSError("selected localisation file no longer exists")
        yml_encoding = "utf-8-sig"
        existing_yml_text = ""
        if yml_exists:
            existing_yml_text, yml_encoding = read_file_with_encoding(loc_file)
            if existing_yml_text is None or yml_encoding is None:
                raise OSError("localisation file could not be read")
            for line in existing_yml_text.splitlines():
                m = _LOC_KEY.match(line)
                if m:
                    existing_yml_keys.add(m.group(1))

        to_add = []
        for ln in yml_new_lines:
            m = _LOC_KEY.match(ln)
            # If the line doesn't look like a loc key, keep it as-is (header/comment).
            if not m:
                to_add.append(ln)
            elif m.group(1) not in existing_yml_keys:
                to_add.append(ln)

        if to_add:
            if not yml_exists:
                wf.write_text(loc_file, loc_header + "\n", encoding=yml_encoding)
            # Only add the section header if it's not already there
            needs_hdr = f"##########Events - {ns}##########" not in existing_yml_text
            loc_body = ""
            if needs_hdr:
                loc_body += f"\n ##########Events - {ns}##########\n"
            loc_body += "\n".join(to_add) + "\n"
            wf.append_text(loc_file, loc_body, encoding=yml_encoding)
            rel = os.path.relpath(loc_file, mod_root)
            saved.append(f"{rel}  (+{len(to_add)} keys)")
        else:
            warnings.append("No new localisation keys to append.")

    except (OSError, ValueError, RuntimeError, UnicodeDecodeError) as exc:
        errs.append("Localisation: " + str(exc))

    # ── SCRIPTED LOC ─────────────────────────────────────────────────
    if mod.edit_scripted_loc_file:
        sloc_blocks = build_event_scripted_loc_blocks(ev.eid for ev in events)
        append_scripted_loc(
            mod.edit_scripted_loc_file,
            sloc_blocks,
            saved,
            errs,
            mod_root,
            require_existing=True,
        )

    return saved, warnings, errs


def _replace_or_append_block(src, block_id, new_block):
    """Replace the top-level ``block_id = { ... }`` in ``src``, or append it."""
    pattern = re.compile(r"^[ \t]*" + re.escape(block_id) + r"\s*=\s*\{", re.MULTILINE)
    m = pattern.search(src)
    style = newline_style(src)
    generated = convert_newlines(new_block, style)
    if not m:
        # Not found — append without rewriting existing bytes.
        return (
            src + convert_newlines("\n\n" + new_block + "\n", style),
            "appended",
        )
    i = match_brace(src, m.end() - 1)
    if i < len(src):
        replaced = src[: m.start()] + generated + src[i + 1 :]
        return replaced, "updated"
    return (
        src + convert_newlines("\n\n" + new_block + "\n", style),
        "appended",
    )


def save_dyn_mod(
    mod, mod_root, *, mid, icon, name, desc, scope, enable, mod_entries, const_lines
):
    """Write one dynamic modifier, its localisation, focus snippet and icon sprite.

    ``mod_entries`` is ``(modifier, variable, tooltip)`` triples. Returns
    ``(results, errors)``; each result is ``(relative path, action, note)``.
    """
    results = []  # (rel_path, action, note)
    errors = []
    workspace_files = notifying_workspace_files(mod, mod_root)

    def full(rel):
        return os.path.join(mod_root, rel)

    def record_read_error(rel):
        message = f"Could not read existing file: {rel}"
        add_error(message)
        errors.append(message)

    def write(rel, content, encoding="utf-8"):
        p = full(rel)
        try:
            workspace_files.write_text(p, content, encoding=encoding)
            return True
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            errors.append(f"{rel}: {exc}")
            return False

    # ════════════════════════════════════════════════════════
    # FILE 1 — common/dynamic_modifiers/  (one file per modifier)
    # Strategy: if file exists, replace the block for `mid`;
    #           if not, create it fresh.
    # ════════════════════════════════════════════════════════
    dm_rel = os.path.join("common", "dynamic_modifiers", f"{mid}.txt")
    dm_state, dm_existing, dm_encoding = _read_existing_file_with_encoding(full(dm_rel))
    dm_encoding = dm_encoding or "utf-8"

    # Build the new block
    icon_gfx = (icon if icon.startswith("GFX_") else f"GFX_idea_{icon}") if icon else ""
    dm_block_lines = [f"{mid} = {{"]
    if scope != "country":
        dm_block_lines.append(f"\tscope = {scope}")
    if icon_gfx:
        dm_block_lines.append(f"\ticon = {icon_gfx}")
    if enable:
        dm_block_lines.append("\tenable = {")
        for ln in enable.splitlines():
            if ln.strip():
                dm_block_lines.append(f"\t\t{ln.strip()}")
        dm_block_lines.append("\t}")
    dm_block_lines.append("")
    for modifier, var, _ in mod_entries:
        dm_block_lines.append(f"\t{modifier} = {var}")
    if const_lines:
        dm_block_lines.append("")
        for ln in const_lines:
            dm_block_lines.append(f"\t{ln}")
    dm_block_lines.append("}")
    dm_new_block = "\n".join(dm_block_lines)

    if dm_state == _READ_FAILED:
        record_read_error(dm_rel)
    else:
        if dm_state == _READ_MISSING:
            # Fresh file
            dm_final = dm_new_block + "\n"
            action = "created"
        else:
            # Replace existing block for `mid` if present, else append
            dm_final, action = _replace_or_append_block(
                dm_existing or "", mid, dm_new_block
            )

        if write(dm_rel, dm_final, dm_encoding):
            results.append((dm_rel, action, f"{len(mod_entries)} variable modifiers"))

    # ════════════════════════════════════════════════════════
    # FILE 2 — configured localisation language
    # Strategy: scan all configured-language .yml files
    # for existing keys; only add missing ones.
    # Write to the configured target filename (create or append).
    # ════════════════════════════════════════════════════════
    loc_target = mod.loc_target
    existing_keys = set()

    # Collect all keys already in any loc file
    # Accept both modern `key: "value"` and legacy `key:0 "value"` forms
    for loc_path in find_loc_files(mod_root, language=mod.loc_language):
        try:
            content, _encoding = read_file_with_encoding(loc_path)
        except OSError, ValueError, UnicodeDecodeError:
            continue
        if not content:
            continue
        for m in re.finditer(r'^\s+(\S+?)(?::\d+)?\s*[=:]?\s*"', content, re.MULTILINE):
            existing_keys.add(m.group(1))

    # Build only the missing entries
    selected_loc = bool(mod.edit_loc_file)
    if selected_loc:
        loc_rel = (
            os.path.relpath(mod.edit_loc_file, mod_root)
            if mod_root
            else mod.edit_loc_file
        )
    else:
        loc_rel = os.path.join(
            "localisation",
            loc_target.dirname(),
            loc_target.filename(mid),
        )
    loc_state, loc_existing, loc_encoding = _read_existing_file_with_encoding(
        full(loc_rel)
    )
    loc_read_failed = loc_state == _READ_FAILED
    if selected_loc and loc_state == _READ_MISSING:
        loc_read_failed = True

    new_loc_lines = []

    def add_loc(key, value):
        if key not in existing_keys:
            new_loc_lines.append(f" {key}: {json.dumps(value, ensure_ascii=False)}")

    if not loc_read_failed:
        add_loc(mid, name)
        add_loc(f"{mid}_desc", desc)
        add_loc("modifies_dynamic_modifier_tt", "Modifies $MODIFIER$")
        for modifier, _var, tooltip in mod_entries:
            if tooltip:
                add_loc(tooltip, modifier.replace("_", " ").title())

    if loc_read_failed:
        record_read_error(loc_rel)
    elif new_loc_lines:
        loc_encoding = loc_encoding or "utf-8-sig"
        if loc_state == _READ_MISSING:
            loc_final = loc_target.header() + "\n" + "\n".join(new_loc_lines) + "\n"
            loc_action = "created"
        else:
            # Append without rewriting the existing bytes.
            loc_source = loc_existing or ""
            inserted = convert_newlines(
                "\n\n"
                + f" # {mid} — added by Focus Maker\n"
                + "\n".join(new_loc_lines)
                + "\n",
                newline_style(loc_source),
            )
            loc_final = loc_source + inserted
            loc_action = f"appended {len(new_loc_lines)} new keys"
        if write(loc_rel, loc_final, loc_encoding):
            results.append((loc_rel, loc_action, f"{len(new_loc_lines)} loc keys"))
    else:
        results.append((loc_rel, "skipped", "all keys already exist"))

    # ════════════════════════════════════════════════════════
    # FILE 3 — focus snippet (always overwrite — it's a helper)
    # ════════════════════════════════════════════════════════
    snip_rel = os.path.join("_focus_snippets", f"{mid}_focus_snippet.txt")
    snippet = [
        "# ============================================================",
        f"# Focus snippet for: {mid}",
        "# ============================================================",
        "",
        "# ── ACTIVATION focus (first time adding this modifier) ────────",
        "# Use adds_dynamic_modifier_tt when the block contains add_dynamic_modifier",
        f"\t\t\tadd_dynamic_modifier = {{ modifier = {mid} }}",
        "\t\t\tcustom_effect_tooltip = {",
        "\t\t\t\tlocalization_key = adds_dynamic_modifier_tt",
        f"\t\t\t\tMODIFIER = {mid}",
        "\t\t\t}",
        "",
        "# ── MODIFICATION focus (changing variables only, no add_dynamic_modifier) ─",
        "# Use modifies_dynamic_modifier_tt when only variables are changed",
        "\t\t\tcustom_effect_tooltip = {",
        "\t\t\t\tlocalization_key = modifies_dynamic_modifier_tt",
        f"\t\t\t\tMODIFIER = {mid}",
        "\t\t\t}",
    ]
    for _modifier, var, tooltip in mod_entries:
        tt = f" tooltip = {tooltip}" if tooltip else ""
        snippet.append(f"\t\t\tadd_to_variable = {{ {var} = 0.05{tt} }}")
    if write(snip_rel, "\n".join(snippet) + "\n"):
        results.append((snip_rel, "created", "paste into your focus file"))

    # ════════════════════════════════════════════════════════
    # FILE 4 — interface/ideas.gfx (if icon set)
    # ════════════════════════════════════════════════════════
    if icon_gfx:
        icon_name = icon_gfx.replace("GFX_idea_", "").replace("GFX_", "")
        gfx_rel = os.path.join("interface", "ideas.gfx")
        gfx_state, gfx_existing, gfx_encoding = _read_existing_file_with_encoding(
            full(gfx_rel)
        )
        if gfx_state == _READ_FAILED:
            record_read_error(gfx_rel)
        else:
            gfx_source = None if gfx_state == _READ_MISSING else gfx_existing
            gfx_final, added_count = append_sprite_types(
                gfx_source,
                [(icon_gfx, f"gfx/interface/ideas/{icon_name}.dds")],
            )
            if added_count:
                gfx_action = (
                    "created" if gfx_state == _READ_MISSING else "appended sprite"
                )
                if write(gfx_rel, gfx_final, gfx_encoding or "utf-8"):
                    results.append(
                        (
                            gfx_rel,
                            gfx_action,
                            f"icon: {icon_gfx} → gfx/interface/ideas/{icon_name}.dds",
                        )
                    )
            else:
                results.append((gfx_rel, "skipped (icon already defined)", ""))

    return results, errors


def save_decisions(
    mod,
    mod_root,
    *,
    ns,
    dec_path,
    cat_path,
    render_decisions,
    render_categories,
    render_yml,
    sloc_blocks,
):
    """Write the decisions and categories files and append their localisation.

    A file chosen as an edit target is rewritten in its own encoding and
    newline style. Each renderer runs just before its file is written.
    Returns ``(saved, errs)`` for ``format_save_summary``.
    """
    saved = []
    errs = []
    wf = notifying_workspace_files(mod, mod_root)
    selected_dec = bool(mod.edit_decisions_file)
    selected_cat = bool(mod.edit_decisions_cat_file)
    try:
        dec_encoding = "utf-8"
        existing_dec = ""
        if selected_dec:
            existing_dec, dec_encoding = read_file_with_encoding(dec_path)
            if existing_dec is None or dec_encoding is None:
                raise OSError("selected decisions file could not be read")
        decisions_text = render_decisions()
        if selected_dec:
            decisions_text = convert_newlines(
                decisions_text, newline_style(existing_dec)
            )
        wf.write_text(dec_path, decisions_text, encoding=dec_encoding)
        try:
            saved.append(os.path.relpath(dec_path, mod_root))
        except ValueError:
            saved.append(dec_path)
    except OSError as e:
        errs.append(str(e))
        get_logger("decision").error("save decisions failed: %s", e, exc_info=True)
    try:
        cat_encoding = "utf-8"
        existing_cat = ""
        if selected_cat:
            existing_cat, cat_encoding = read_file_with_encoding(cat_path)
            if existing_cat is None or cat_encoding is None:
                raise OSError("selected decision categories file could not be read")
        categories_text = render_categories()
        if selected_cat:
            categories_text = convert_newlines(
                categories_text, newline_style(existing_cat)
            )
        wf.write_text(cat_path, categories_text, encoding=cat_encoding)
        try:
            saved.append(os.path.relpath(cat_path, mod_root))
        except ValueError:
            saved.append(cat_path)
    except OSError as e:
        errs.append(str(e))
        get_logger("decision").error("save categories failed: %s", e, exc_info=True)
    loc_target = mod.loc_target
    selected_loc = bool(mod.edit_loc_file)
    yml_path = (
        mod.edit_loc_file
        if selected_loc
        else os.path.join(
            mod_root,
            "localisation",
            loc_target.dirname(),
            loc_target.filename(f"{ns}_decisions"),
        )
    )
    try:
        # Read existing keys
        existing_loc_keys = set()
        yml_exists = os.path.isfile(yml_path)
        yml_encoding = "utf-8-sig"
        if selected_loc and not yml_exists:
            raise OSError("selected localisation file no longer exists")
        if yml_exists:
            existing_yml, yml_encoding = read_file_with_encoding(yml_path)
            if existing_yml is None or yml_encoding is None:
                raise OSError("localisation file could not be read")
            for line in existing_yml.splitlines():
                m = _LOC_KEY.match(line)
                if m:
                    existing_loc_keys.add(m.group(1))
        else:
            wf.write_text(yml_path, loc_target.header() + "\n", encoding=yml_encoding)
        new_lines = [
            line
            for line in render_yml().splitlines()
            if line.strip() and line.strip() != loc_target.header()
        ]
        # Only add lines whose key isn't already in the file
        to_write = []
        for ln in new_lines:
            m = _LOC_KEY.match(ln)
            if m and m.group(1) in existing_loc_keys:
                continue
            to_write.append(ln)
        if to_write:
            wf.append_text(yml_path, "\n".join(to_write) + "\n", encoding=yml_encoding)
        saved.append(os.path.relpath(yml_path, mod_root) + f"  (+{len(to_write)} keys)")
    except OSError as e:
        errs.append(str(e))
        get_logger("decision").error("save loc failed: %s", e, exc_info=True)
    # ── SCRIPTED LOC ─────────────────────────────────────────────────
    if mod.edit_scripted_loc_file:
        append_scripted_loc(
            mod.edit_scripted_loc_file,
            sloc_blocks,
            saved,
            errs,
            mod_root,
            require_existing=True,
        )

    return saved, errs
