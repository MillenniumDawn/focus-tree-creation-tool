"""Serialize focus objects back to HOI4 focus-tree script text.

Pure string building: no tkinter and no file I/O. The caller owns reading and
writing the file.
"""

import re

from hoi4cm.script.effects import render_effect
from hoi4cm.script.syntax import emit_scalar, serialize_block

from .codec import render_focus_body
from .operations import build_focus_name_lookup

GFX_DEFAULT = "GFX_goal_generic_political_pressure"


def _emit_focus_id(name):
    """Render a focus id without allowing an embedded quote to escape it.

    Clausewitz has no string escape syntax, so ``emit_scalar`` deliberately
    rejects double quotes. Focus ids can still arrive from hand-edited input
    containing one; replace that impossible character before making the normal
    scalar decision so export produces a parseable id instead of raw script.
    """
    try:
        return emit_scalar(name)
    except ValueError:
        return emit_scalar(name.replace('"', "_"))


def _country_raw_lines(country_raw):
    """Return country-body lines with unmatched braces neutralized.

    Imported country blocks are normally balanced, but project data can be
    edited independently of the parsed source. An unmatched ``}`` in that
    data would close the generated ``country`` block and inject following
    script at tree level. Preserve balanced content verbatim and comment only
    the first unmatched closer on a line; close unfinished nested blocks so
    later output remains inside the country block.
    """
    lines = []
    depth = 0
    in_quote = False
    for line in country_raw.splitlines():
        rendered = []
        index = 0
        while index < len(line):
            char = line[index]
            if char == '"':
                in_quote = not in_quote
                rendered.append(char)
            elif char == "#" and not in_quote:
                rendered.append(line[index:])
                break
            elif not in_quote and char == "{":
                depth += 1
                rendered.append(char)
            elif not in_quote and char == "}":
                if depth == 0:
                    rendered.append("#" + line[index:])
                    break
                depth -= 1
                rendered.append(char)
            else:
                rendered.append(char)
            index += 1
        if "".join(rendered).strip():
            lines.append("".join(rendered))

    if in_quote:
        lines.append('"')
    for closing_depth in range(depth, 0, -1):
        lines.append("\t" * (closing_depth - 1) + "}")
    return lines


def _emit_tree_extras(out, info):
    """Re-emit unrecognized focus_tree wrapper keys captured at parse time.

    Mirrors how ``_script_extras`` preserves unknown per-focus keys — see
    ``codec.render_focus_body``.
    """
    tree_extras = info.get("tree_extras") or {}
    if not tree_extras:
        return
    rendered = serialize_block(
        tree_extras, indent="\t", include_bare_values=True, strip_strings=True
    )
    if rendered:
        out.extend(rendered.splitlines())
        out.append("")


def export_focus_tree(
    focuses_in_tree,
    info,
    *,
    focus_lookup,
    effect_renderer=render_effect,
    focus_name_lookup=None,
):
    """Return the full script text for one extra (shared/joint) tree.

    ``focuses_in_tree`` is the list of focuses to write. ``info`` is the tree
    metadata dict (``tree_id``, ``country_tag``, ``cfp_x``/``cfp_y``, ``type``,
    ``had_wrapper``, ``shared_focuses``, ``joint_focuses``, ``country_raw`` —
    the verbatim ``country = { ... }`` body captured on import, blank falls
    back to the canned block — and ``tree_extras``, other unrecognized
    ``focus_tree`` wrapper keys such as ``default`` or ``reset_on_civilwar``).
    ``focus_lookup`` is a ``{id: Focus}`` mapping covering every loaded focus
    (for prerequisite / mutex / relative-position name resolution).
    ``effect_renderer`` renders one effect dict to script text.
    """
    tid = re.sub(r"[^A-Za-z0-9_]", "_", info["tree_id"].strip()) or "TAG_focus_tree"
    country_tag = info.get("country_tag", "TAG")
    cfp_x = info.get("cfp_x")
    cfp_y = info.get("cfp_y")
    is_joint = info.get("type") == "joint"

    # name → focus, built once (keep first match) so relative_position_id
    # resolution below is O(1) per focus instead of scanning all focuses.
    name_to_focus = (
        build_focus_name_lookup(focus_lookup.values())
        if focus_name_lookup is None
        else focus_name_lookup
    )

    def write_focus_body(focus, out, indent):
        out.extend(
            render_focus_body(
                focus,
                focus_lookup=focus_lookup,
                focus_name_lookup=name_to_focus,
                indent=indent,
                effect_renderer=effect_renderer,
                coordinate_policy="raw",
                completion_reward_policy="extra",
                include_joint_extra=True,
            )
        )

    out = []
    had_wrapper = info.get("had_wrapper", False)
    if is_joint or not had_wrapper:
        # Bare blocks without a focus_tree wrapper:
        #   joint trees               -> joint_focus = { ... }
        #   shared trees (no wrapper) -> shared_focus = { ... }
        block_kw = "joint_focus" if is_joint else "shared_focus"
        for f in focuses_in_tree:
            out.append(f"{block_kw} = {{")
            out.append(f"\tid = {_emit_focus_id(f.name)}")
            out.append(f"\ticon = {emit_scalar(getattr(f, 'gfx', GFX_DEFAULT))}")
            write_focus_body(f, out, "\t")
            out.append("}")
            out.append("")
    else:
        # Shared tree with focus_tree = { } wrapper -> focus = { } blocks inside.
        out.append("focus_tree = {")
        out.append(f"\tid = {tid}")
        out.append("")
        country_raw = (info.get("country_raw") or "").strip()
        out.append("\tcountry = {")
        if country_raw:
            for ln in _country_raw_lines(country_raw):
                out.append(f"\t\t{ln}")
        else:
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
        _emit_tree_extras(out, info)
        for f in focuses_in_tree:
            out.append("\tfocus = {")
            out.append(f"\t\tid = {_emit_focus_id(f.name)}")
            out.append(f"\t\ticon = {emit_scalar(getattr(f, 'gfx', GFX_DEFAULT))}")
            write_focus_body(f, out, "\t\t")
            out.append("\t}")
            out.append("")
        out.append("}")
    return "\n".join(out)


def export_main_tree(
    focuses_in_tree,
    info,
    *,
    focus_lookup,
    effect_renderer=render_effect,
    focus_name_lookup=None,
):
    """Return the full script text for the main focus tree (``tree_idx == 0``).

    ``focuses_in_tree`` is the main tree's focuses, in display order. ``info``
    is the tree metadata dict: ``tree_id``, ``country_tag``, ``cfp_x``/``cfp_y``
    (``None`` to auto-derive from the focuses), ``country_raw`` (the verbatim
    ``country = { ... }`` body captured on import — blank falls back to the
    MD-convention default block), ``shared_focuses``/``joint_focuses``
    (reference lines preserved from import), and ``tree_extras`` (other
    unrecognized ``focus_tree`` wrapper keys, such as ``default`` or
    ``reset_on_civilwar``, preserved verbatim). ``focus_lookup`` is the full
    ``{id: Focus}`` map (every loaded focus, including linked focuses) used to
    resolve prerequisite/mutex/relative-position names. ``effect_renderer``
    renders one effect dict to script text, exactly like ``export_focus_tree``.

    Both exporters use the canonical focus body codec. This path selects main
    tree coordinate and completion-reward policies.
    """
    tid = re.sub(r"[^A-Za-z0-9_]", "_", info["tree_id"].strip()) or "TAG_focus_tree"
    country_tag = info.get("country_tag", "TAG")
    cfp_x = info.get("cfp_x")
    cfp_y = info.get("cfp_y")

    name_to_focus = (
        build_focus_name_lookup(focus_lookup.values())
        if focus_name_lookup is None
        else focus_name_lookup
    )

    out = []
    out.append("focus_tree = {")
    out.append(f"\tid = {tid}")
    out.append("")

    country_raw = (info.get("country_raw") or "").strip()
    out.append("\tcountry = {")
    if country_raw:
        for ln in _country_raw_lines(country_raw):
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
    _emit_tree_extras(out, info)

    for f in focuses_in_tree:
        out.append("\tfocus = {")
        out.append(f"\t\tid = {_emit_focus_id(f.name)}")
        out.append(f"\t\ticon = {emit_scalar(getattr(f, 'gfx', GFX_DEFAULT))}")
        out.extend(
            render_focus_body(
                f,
                focus_lookup=focus_lookup,
                focus_name_lookup=name_to_focus,
                indent="\t\t",
                effect_renderer=effect_renderer,
                coordinate_policy="canvas",
                completion_reward_policy="main",
                include_joint_extra=True,
            )
        )

        out.append("\t}")
        out.append("")

    out.append("}")
    return "\n".join(out)
