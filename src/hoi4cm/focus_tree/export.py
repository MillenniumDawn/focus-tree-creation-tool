"""Serialize focus objects back to HOI4 focus-tree script text.

Pure string building: no tkinter, no file I/O. Cross-tree lookups go through the
``focus_lookup`` mapping and per-effect rendering is delegated to
``effect_renderer`` (the monolith passes its full effect dispatch; tests pass a
minimal ``_raw_block`` renderer). The caller owns reading/writing the file.
"""

import re

GFX_DEFAULT = "GFX_goal_generic_political_pressure"


def _emit_preserved_block(out, key, text, t1, t2):
    """Append ``{t1}key = { ... }``, preserving relative indentation.

    Unlike ``_emit_block`` (which re-indents every line flat), this keeps each
    line's indentation relative to the block's least-indented line — used for
    raw condition blocks (``allow_branch``, ``available``, ``bypass``,
    ``cancel``) where nested sub-blocks must stay nested.
    """
    text = (text or "").strip()
    if not text:
        return
    out.append(f"{t1}{key} = {{")
    lines = text.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    min_ind = (
        min(len(ln) - len(ln.lstrip("\t")) for ln in non_empty) if non_empty else 0
    )
    for ln in lines:
        stripped = ln[min_ind:] if len(ln) >= min_ind else ln.lstrip("\t")
        out.append(f"{t2}{stripped}")
    out.append(f"{t1}}}")


def _emit_block(out, key, text, indent):
    """Append ``{indent}key = { ... }``, one stripped non-blank line per row.

    No-op when ``text`` is blank. Inner lines are indented one tab past ``indent``.
    """
    text = text.strip()
    if not text:
        return
    out.append(f"{indent}{key} = {{")
    for ln in text.splitlines():
        if ln.strip():
            out.append(f"{indent}\t{ln.strip()}")
    out.append(f"{indent}}}")


def export_focus_tree(focuses_in_tree, info, *, focus_lookup, effect_renderer):
    """Return the full script text for one extra (shared/joint) tree.

    ``focuses_in_tree`` is the list of focuses to write. ``info`` is the tree
    metadata dict (``tree_id``, ``country_tag``, ``cfp_x``/``cfp_y``, ``type``,
    ``had_wrapper``, ``shared_focuses``, ``joint_focuses``). ``focus_lookup`` is
    a ``{id: Focus}`` mapping covering every loaded focus (for prerequisite /
    mutex / relative-position name resolution). ``effect_renderer`` renders one
    effect dict to script text.
    """
    tid = re.sub(r"[^A-Za-z0-9_]", "_", info["tree_id"].strip()) or "TAG_focus_tree"
    country_tag = info.get("country_tag", "TAG")
    cfp_x = info.get("cfp_x")
    cfp_y = info.get("cfp_y")
    is_joint = info.get("type") == "joint"

    # name → focus, built once (keep first match) so relative_position_id
    # resolution below is O(1) per focus instead of scanning all focuses.
    name_to_focus = {}
    for foc in focus_lookup.values():
        name_to_focus.setdefault(foc.name, foc)

    def write_focus_body(f, out, indent, strip_effect_tab=False):
        """Write the body of a focus block (fields after id/icon).

        strip_effect_tab: effect_renderer emits a 3-tab base indent; set True for
        joint trees where completion_reward is only one level deep.
        """
        t1 = indent
        t2 = indent + "\t"
        ftext = getattr(f, "text", "").strip()
        if ftext:
            out.append(f"{t1}text = {ftext}")
        # Use original file coords (not offset-applied canvas coords) for export.
        gx = getattr(f, "_raw_gx", f.x)
        gy = getattr(f, "_raw_gy", f.y)
        rel_id = getattr(f, "relative_position_id", None)
        if rel_id and rel_id in name_to_focus:
            dx = getattr(f, "_rel_dx", None)
            dy = getattr(f, "_rel_dy", None)
            if dx is None or dy is None:
                parent = name_to_focus.get(rel_id)
                dx = gx - parent.x if parent else gx
                dy = gy - parent.y if parent else gy
            out.append(f"{t1}x = {dx}")
            out.append(f"{t1}y = {dy}")
            out.append(f"{t1}relative_position_id = {rel_id}")
        else:
            out.append(f"{t1}x = {gx}")
            out.append(f"{t1}y = {gy}")
        for off in getattr(f, "offsets", []):
            out.append(f"{t1}offset = {{")
            out.append(f"{t1}\tx = {off['x']}")
            out.append(f"{t1}\ty = {off['y']}")
            if off.get("trigger", "").strip():
                out.append(f"{t1}\ttrigger = {{")
                for ln in off["trigger"].strip().splitlines():
                    out.append(f"{t1}\t\t{ln.strip()}")
                out.append(f"{t1}\t}}")
            out.append(f"{t1}}}")
        out.append(f"{t1}cost = {f.cost}")
        # Joint-specific preserved fields (joint_trigger only — offset in f.offsets).
        jextra = getattr(f, "_joint_extra", "").strip()
        if jextra:
            for ln in jextra.splitlines():
                out.append(f"{t1}{ln}")
        if f.prereqs:
            for grp in f.prereqs:
                valid = [p for p in grp if p in focus_lookup]
                if not valid:
                    continue
                inner = " ".join(f"focus = {focus_lookup[p].name}" for p in valid)
                out.append(f"{t1}prerequisite = {{ {inner} }}")
        if f.mutex:
            for mid in f.mutex:
                if mid in focus_lookup:
                    out.append(
                        f"{t1}mutually_exclusive = "
                        f"{{ focus = {focus_lookup[mid].name} }}"
                    )
        sf = getattr(f, "search_filters", "").strip()
        if sf:
            out.append(f"{t1}search_filters = {{ {sf} }}")
        _emit_preserved_block(
            out, "allow_branch", getattr(f, "allow_branch", ""), t1, t2
        )
        for cond_key, cond_attr in [
            ("available", "available_cond"),
            ("bypass", "bypass_cond"),
            ("cancel", "cancel_cond"),
        ]:
            _emit_preserved_block(out, cond_key, getattr(f, cond_attr, ""), t1, t2)
        # will_lead_to_war_with / complete_tooltip / select_effect — preserve.
        wltww = getattr(f, "will_lead_to_war_with", "").strip()
        if wltww:
            out.append(f"{t1}will_lead_to_war_with = {wltww}")
        _emit_block(out, "complete_tooltip", getattr(f, "complete_tooltip", ""), t1)
        _emit_block(out, "select_effect", getattr(f, "select_effect", ""), t1)
        if not f.cancel_if_invalid:
            out.append(f"{t1}cancel_if_invalid = no")
        if f.continue_if_invalid:
            out.append(f"{t1}continue_if_invalid = yes")
        if f.available_if_capitulated:
            out.append(f"{t1}available_if_capitulated = yes")
        out.append("")
        out.append(f"{t1}completion_reward = {{")
        if f.effects:
            for eff in f.effects:
                eff_text = effect_renderer(eff)
                if strip_effect_tab:
                    # renderer uses \t\t\t base indent; joint needs \t\t
                    eff_text = "\n".join(
                        ln[1:] if ln.startswith("\t") else ln
                        for ln in eff_text.splitlines()
                    )
                out.append(eff_text)
        else:
            out.append(
                f'{t2}log = "[GetDateText]: [This.GetName]: '
                f'focus {f.name} executed"'
            )
            out.append(f"{t2}# TODO: add effects")
        out.append(f"{t1}}}")
        _emit_block(out, "bypass_effect", getattr(f, "bypass_effect", ""), t1)
        out.append("")
        out.append(f"{t1}ai_will_do = {{")
        raw_ai = getattr(f, "ai_will_do_raw", "").strip()
        if raw_ai:
            for ln in raw_ai.splitlines():
                out.append(f"{t2}{ln.strip()}")
        else:
            out.append(f"{t2}base = {f.ai_will_do}")
        out.append(f"{t1}}}")

    out = []
    had_wrapper = info.get("had_wrapper", False)
    if is_joint or not had_wrapper:
        # Bare blocks without a focus_tree wrapper:
        #   joint trees               -> joint_focus = { ... }
        #   shared trees (no wrapper) -> shared_focus = { ... }
        block_kw = "joint_focus" if is_joint else "shared_focus"
        for f in focuses_in_tree:
            out.append(f"{block_kw} = {{")
            out.append(f"\tid = {f.name}")
            out.append(f"\ticon = {getattr(f, 'gfx', GFX_DEFAULT)}")
            write_focus_body(f, out, "\t", strip_effect_tab=True)
            out.append("}")
            out.append("")
    else:
        # Shared tree with focus_tree = { } wrapper -> focus = { } blocks inside.
        out.append("focus_tree = {")
        out.append(f"\tid = {tid}")
        out.append("")
        out.append("\tcountry = {")
        out.append("\t\tfactor = 0")
        out.append("\t\tmodifier = {")
        out.append("\t\t\tadd = 20")
        out.append(f"\t\t\toriginal_tag = {country_tag}")
        out.append("\t\t}")
        out.append("\t}")
        out.append("")
        for sf in info.get("shared_focuses", []):
            out.append(f"\tshared_focus = {sf}")
        for jf in info.get("joint_focuses", []):
            out.append(f"\tjoint_focus = {jf}")
        if info.get("shared_focuses") or info.get("joint_focuses"):
            out.append("")
        if cfp_x is None or cfp_y is None:
            if focuses_in_tree:
                cfp_x = min(f.x for f in focuses_in_tree) * 100
                cfp_y = max(f.y for f in focuses_in_tree) * 100
            else:
                cfp_x = cfp_y = 0
        out.append(f"\tcontinuous_focus_position = {{ x = {cfp_x} y = {cfp_y} }}")
        out.append("")
        for f in focuses_in_tree:
            out.append("\tfocus = {")
            out.append(f"\t\tid = {f.name}")
            out.append(f"\t\ticon = {getattr(f, 'gfx', GFX_DEFAULT)}")
            write_focus_body(f, out, "\t\t")
            out.append("\t}")
            out.append("")
        out.append("}")
    return "\n".join(out)


def export_main_tree(focuses_in_tree, info, *, focus_lookup, effect_renderer):
    """Return the full script text for the main focus tree (``tree_idx == 0``).

    ``focuses_in_tree`` is the main tree's focuses, in display order. ``info``
    is the tree metadata dict: ``tree_id``, ``country_tag``, ``cfp_x``/``cfp_y``
    (``None`` to auto-derive from the focuses), ``country_raw`` (the verbatim
    ``country = { ... }`` body captured on import — blank falls back to the
    MD-convention default block), and ``shared_focuses``/``joint_focuses``
    (reference lines preserved from import). ``focus_lookup`` is the full
    ``{id: Focus}`` map (every loaded focus, including linked focuses) used to
    resolve prerequisite/mutex/relative-position names. ``effect_renderer``
    renders one effect dict to script text, exactly like ``export_focus_tree``.

    The main tree diverges from ``export_focus_tree``'s shared/joint path
    enough (a ``text`` override line, ``allow_branch``, the boolean flag
    fields, a different completion_reward default) that it gets its own body
    writer here rather than reusing ``write_focus_body``.
    """
    tid = re.sub(r"[^A-Za-z0-9_]", "_", info["tree_id"].strip()) or "TAG_focus_tree"
    country_tag = info.get("country_tag", "TAG")
    cfp_x = info.get("cfp_x")
    cfp_y = info.get("cfp_y")

    name_to_focus = {}
    for foc in focus_lookup.values():
        name_to_focus.setdefault(foc.name, foc)

    out = []
    out.append("focus_tree = {")
    out.append(f"\tid = {tid}")
    out.append("")

    country_raw = (info.get("country_raw") or "").strip()
    out.append("\tcountry = {")
    if country_raw:
        for ln in country_raw.splitlines():
            if ln.strip():
                out.append(f"\t\t{ln}")
    else:
        out.append("\t\tbase = 0")
        out.append("\t\tmodifier = {")
        out.append("\t\t\tadd = 100")
        out.append(f"\t\t\toriginal_tag = {country_tag}")
        out.append("\t\t}")
    out.append("\t}")
    out.append("")

    for sf in info.get("shared_focuses", []):
        out.append(f"\tshared_focus = {sf}")
    for jf in info.get("joint_focuses", []):
        out.append(f"\tjoint_focus = {jf}")
    if info.get("shared_focuses") or info.get("joint_focuses"):
        out.append("")

    if cfp_x is None or cfp_y is None:
        if focuses_in_tree:
            cfp_x = min(f.x for f in focuses_in_tree) * 100
            cfp_y = max(f.y for f in focuses_in_tree) * 100
        else:
            cfp_x = cfp_y = 0
    out.append(f"\tcontinuous_focus_position = {{ x = {cfp_x} y = {cfp_y} }}")
    out.append("")

    for f in focuses_in_tree:
        out.append("\tfocus = {")
        out.append(f"\t\tid = {f.name}")
        out.append(f"\t\ticon = {getattr(f, 'gfx', GFX_DEFAULT)}")
        ftext = getattr(f, "text", "").strip()
        if ftext:
            out.append(f"\t\ttext = {ftext}")

        gx, gy = f.x, f.y
        rel_id = getattr(f, "relative_position_id", None)
        parent = name_to_focus.get(rel_id) if rel_id else None
        if parent:
            dx = getattr(f, "_rel_dx", None)
            dy = getattr(f, "_rel_dy", None)
            if dx is None or dy is None:
                dx = gx - parent.x
                dy = gy - parent.y
            out.append(f"\t\tx = {dx}")
            out.append(f"\t\ty = {dy}")
            out.append(f"\t\trelative_position_id = {rel_id}")
        else:
            out.append(f"\t\tx = {gx}")
            out.append(f"\t\ty = {gy}")

        for off in getattr(f, "offsets", []):
            out.append("\t\toffset = {")
            out.append(f"\t\t\tx = {off['x']}")
            out.append(f"\t\t\ty = {off['y']}")
            if off.get("trigger", "").strip():
                out.append("\t\t\ttrigger = {")
                for ln in off["trigger"].strip().splitlines():
                    out.append(f"\t\t\t\t{ln.strip()}")
                out.append("\t\t\t}")
            out.append("\t\t}")

        out.append(f"\t\tcost = {f.cost}")

        if f.prereqs:
            for grp in f.prereqs:
                valid = [p for p in grp if p in focus_lookup]
                if not valid:
                    continue
                inner = " ".join(f"focus = {focus_lookup[p].name}" for p in valid)
                out.append(f"\t\tprerequisite = {{ {inner} }}")

        if f.mutex:
            for mid in f.mutex:
                if mid in focus_lookup:
                    out.append(
                        f"\t\tmutually_exclusive = "
                        f"{{ focus = {focus_lookup[mid].name} }}"
                    )

        sf = getattr(f, "search_filters", "").strip()
        if sf:
            out.append(f"\t\tsearch_filters = {{ {sf} }}")

        _emit_preserved_block(
            out, "allow_branch", getattr(f, "allow_branch", ""), "\t\t", "\t\t\t"
        )
        _emit_preserved_block(
            out, "available", getattr(f, "available_cond", ""), "\t\t", "\t\t\t"
        )
        _emit_preserved_block(
            out, "bypass", getattr(f, "bypass_cond", ""), "\t\t", "\t\t\t"
        )
        _emit_preserved_block(
            out, "cancel", getattr(f, "cancel_cond", ""), "\t\t", "\t\t\t"
        )

        wltww = getattr(f, "will_lead_to_war_with", "").strip()
        if wltww:
            out.append(f"\t\twill_lead_to_war_with = {wltww}")
        _emit_block(out, "complete_tooltip", getattr(f, "complete_tooltip", ""), "\t\t")
        _emit_block(out, "select_effect", getattr(f, "select_effect", ""), "\t\t")

        if not f.cancel_if_invalid:
            out.append("\t\tcancel_if_invalid = no")
        if f.continue_if_invalid:
            out.append("\t\tcontinue_if_invalid = yes")
        if f.available_if_capitulated:
            out.append("\t\tavailable_if_capitulated = yes")

        # Preserve an imported raw completion_reward verbatim; only inject the
        # hardcoded log line when there's no raw block, to avoid duplicating
        # it on every save.
        has_raw_reward = bool(
            f.effects and any(e.get("type") == "_raw_block" for e in f.effects)
        )
        out.append("")
        out.append("\t\tcompletion_reward = {")
        if not has_raw_reward:
            out.append(f'\t\t\tlog = "[GetDateText]: [Root.GetName]: Focus {f.name}"')
        if f.effects:
            for eff in f.effects:
                out.append(effect_renderer(eff))
        else:
            out.append("\t\t\t# TODO: add effects")
        out.append("\t\t}")

        _emit_block(out, "bypass_effect", getattr(f, "bypass_effect", ""), "\t\t")

        out.append("")
        out.append("\t\tai_will_do = {")
        raw_ai = getattr(f, "ai_will_do_raw", "").strip()
        if raw_ai:
            for ln in raw_ai.splitlines():
                out.append(f"\t\t\t{ln.strip()}")
        else:
            out.append(f"\t\t\tbase = {f.ai_will_do}")
        out.append("\t\t}")

        out.append("\t}")
        out.append("")

    out.append("}")
    return "\n".join(out)
