"""Serialize focus objects back to HOI4 focus-tree script text.

Pure string building: no tkinter, no file I/O. Cross-tree lookups go through the
``focus_lookup`` mapping and per-effect rendering is delegated to
``effect_renderer`` (the monolith passes its full effect dispatch; tests pass a
minimal ``_raw_block`` renderer). The caller owns reading/writing the file.
"""

import re

GFX_DEFAULT = "GFX_goal_generic_political_pressure"


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

    def write_focus_body(f, out, indent, strip_effect_tab=False):
        """Write the body of a focus block (fields after id/icon).

        strip_effect_tab: effect_renderer emits a 3-tab base indent; set True for
        joint trees where completion_reward is only one level deep.
        """
        t1 = indent
        t2 = indent + "\t"
        # Use original file coords (not offset-applied canvas coords) for export.
        gx = getattr(f, "_raw_gx", f.x)
        gy = getattr(f, "_raw_gy", f.y)
        rel_id = getattr(f, "relative_position_id", None)
        if rel_id and any(foc.name == rel_id for foc in focus_lookup.values()):
            dx = getattr(f, "_rel_dx", None)
            dy = getattr(f, "_rel_dy", None)
            if dx is None or dy is None:
                parent = next(
                    (foc for foc in focus_lookup.values() if foc.name == rel_id),
                    None,
                )
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
        for cond_key, cond_attr in [
            ("available", "available_cond"),
            ("bypass", "bypass_cond"),
            ("cancel", "cancel_cond"),
        ]:
            cond = getattr(f, cond_attr, "").strip()
            if cond:
                out.append(f"{t1}{cond_key} = {{")
                lines = cond.splitlines()
                non_empty = [ln for ln in lines if ln.strip()]
                min_ind = (
                    min(len(ln) - len(ln.lstrip("\t")) for ln in non_empty)
                    if non_empty
                    else 0
                )
                for ln in lines:
                    stripped = ln[min_ind:] if len(ln) >= min_ind else ln.lstrip("\t")
                    out.append(f"{t2}{stripped}")
                out.append(f"{t1}}}")
        # will_lead_to_war_with / complete_tooltip / select_effect — preserve.
        wltww = getattr(f, "will_lead_to_war_with", "").strip()
        if wltww.startswith("{") and wltww.endswith("}"):
            wltww = wltww[1:-1].strip()
        _emit_block(out, "will_lead_to_war_with", wltww, t1)
        _emit_block(out, "complete_tooltip", getattr(f, "complete_tooltip", ""), t1)
        _emit_block(out, "select_effect", getattr(f, "select_effect", ""), t1)
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
