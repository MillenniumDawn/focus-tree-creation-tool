"""Low-level HOI4 script marshalling helpers."""


def dict_to_raw(d, indent="\t"):
    """Recursively convert a parsed dict back to HOI4 script lines.

    Handles nested dicts, repeated keys (lists), and bools (True→yes, False→no).
    """
    if isinstance(d, bool):
        return "yes" if d else "no"
    if not isinstance(d, dict):
        return str(d)
    lines = []
    for k, v in d.items():
        if str(k).startswith("_"):
            continue
        if isinstance(v, bool):
            lines.append(f"{indent}{k} = {'yes' if v else 'no'}")
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    inner = dict_to_raw(item, indent + "\t")
                    lines.append(f"{indent}{k} = {{\n{inner}\n{indent}}}")
                elif isinstance(item, bool):
                    lines.append(f"{indent}{k} = {'yes' if item else 'no'}")
                else:
                    lines.append(f"{indent}{k} = {item}")
        elif isinstance(v, dict):
            inner = dict_to_raw(v, indent + "\t")
            lines.append(f"{indent}{k} = {{\n{inner}\n{indent}}}")
        else:
            lines.append(f"{indent}{k} = {v}")
    return "\n".join(lines)


def _flat_value(etype, val):
    """Single-value effects that map directly to one field name."""
    mapping = {
        "add_political_power": {"amount": val},
        "add_stability": {"amount": val},
        "add_war_support": {"amount": val},
        "add_ideas": {"idea_name": val},
        "remove_ideas": {"idea_name": val},
        "set_country_flag": {"flag": val},
        "clr_country_flag": {"flag": val},
        "set_global_flag": {"flag": val},
        "release_puppet": {"target": val},
        "give_military_access": {"target": val},
        "add_to_faction": {"target": val},
        "create_faction": {"name": val},
        "custom_effect_tooltip": {"tooltip": val},
        "add_manpower": {"value": val},
        "army_experience": {"value": val},
        "navy_experience": {"value": val},
        "air_experience": {"value": val},
        "complete_national_focus": {"focus_id": val},
    }
    return mapping.get(etype)


def _dict_effect(etype, raw):
    """Handle special-cased effect types whose raw value is a dict."""
    # add_to_variable: {"AM_var": "0.05", "tooltip": "stat_tt"}
    if etype == "add_to_variable":
        clean = {k: v for k, v in raw.items() if not str(k).startswith("_")}
        tooltip = str(clean.pop("tooltip", ""))
        items = list(clean.items())
        if items:
            return {
                "var": str(items[0][0]),
                "value": str(items[0][1]),
                "tooltip": tooltip,
            }
        return {"var": "AM_my_stat_var", "value": "0.05", "tooltip": tooltip}

    # custom_effect_tooltip block form: {"localization_key": ..., "MODIFIER": ...}
    if etype == "custom_effect_tooltip":
        clean = {k: v for k, v in raw.items() if not str(k).startswith("_")}
        if "localization_key" in clean or "MODIFIER" in clean:
            # Preserve the original key; adds_dynamic_modifier_tt vs
            # modifies_dynamic_modifier_tt are semantically different.
            loc_key = str(clean.get("localization_key", "modifies_dynamic_modifier_tt"))
            return {
                "_block_form": "1",
                "localization_key": loc_key,
                "MODIFIER": str(clean.get("MODIFIER", "TAG_modifier")),
            }

    # set_variable raw dict: {"CAN_stability_factor_var": "0.01"}
    if etype == "set_variable":
        clean = {k: v for k, v in raw.items() if not str(k).startswith("_")}
        items = list(clean.items())
        if items:
            return {"var": str(items[0][0]), "value": str(items[0][1])}
        return {"var": "my_var", "value": "0"}

    return None


def normalize_effect_fields(etype, raw, effect_defs):
    """Map raw parsed HOI4 values -> correct EFFECT_DEFS field names.

    The *effect_defs* argument is the effect definition table used to look up
    expected field names; this keeps the helper decoupled from the global
    EFFECT_DEFS constant.
    """
    defn = effect_defs.get(etype, {})
    field_names = [fd[0] for fd in defn.get("fields", [])]

    if isinstance(raw, dict):
        special = _dict_effect(etype, raw)
        if special is not None:
            return special

        clean = {k: v for k, v in raw.items() if not k.startswith("_")}
        if field_names:
            out = {}
            raw_vals = list(clean.values())
            for i, fname in enumerate(field_names):
                if fname in clean:
                    out[fname] = str(clean[fname])
                elif i < len(raw_vals):
                    out[fname] = str(raw_vals[i])
            # carry over any extra keys not in field_names
            for k, v in clean.items():
                if k not in out:
                    out[k] = str(v)
            return out
        return {k: str(v) for k, v in clean.items()}

    val = str(raw).strip()
    flat = _flat_value(etype, val)
    if flat:
        return flat
    if field_names:
        return {field_names[0]: val}
    return {"raw": val}


def append_scripted_loc(sloc_path, blocks, saved, errs, mod_root=None):
    """Append defined_text blocks to a scripted_localisation .txt file.

    blocks: list of dicts with keys:
        name        - the defined_text name (e.g. "GET_TAG_spirit_name")
        texts       - list of (trigger_str, localization_key) tuples
        default     - optional default text string
    """
    if not sloc_path or not blocks:
        return
    import os
    import re

    try:
        os.makedirs(os.path.dirname(sloc_path), exist_ok=True)
        existing = ""
        if os.path.isfile(sloc_path):
            with open(sloc_path, encoding="utf-8", errors="replace") as f:
                existing = f.read()
        new_blocks = []
        for blk in blocks:
            name = blk.get("name", "")
            if not name:
                continue
            # Skip if already defined
            if re.search(
                r"\bdefined_text\s*=\s*\{[^}]*\bname\s*=\s*" + re.escape(name),
                existing,
            ):
                continue
            lines = ["defined_text = {", f"\tname = {name}"]
            for trigger, loc_key in blk.get("texts", []):
                lines.append("\ttext = {")
                if trigger:
                    lines.append(f"\t\ttrigger = {{ {trigger} }}")
                lines.append(f"\t\tlocalization_key = {loc_key}")
                lines.append("\t}")
            if blk.get("default"):
                lines.append("\ttext = {")
                lines.append(f"\t\tlocalization_key = {blk['default']}")
                lines.append("\t}")
            lines.append("}")
            new_blocks.append("\n".join(lines))
        if new_blocks:
            sep = "\n\n" if existing.strip() else ""
            with open(sloc_path, "a", encoding="utf-8") as f:
                f.write(sep + "\n\n".join(new_blocks) + "\n")
            rel = os.path.relpath(sloc_path, mod_root) if mod_root else sloc_path
            saved.append(rel + f"  (+{len(new_blocks)} scripted_loc blocks)")
    except Exception as e:
        errs.append("Scripted Loc: " + str(e))
