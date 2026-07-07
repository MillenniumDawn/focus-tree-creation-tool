"""Build the localisation .yml text for exported focuses.

Pure string building: no file I/O. The caller reads the existing loc file (if
any) and writes the result back; see ``hoi4_content_maker.py``'s ``_export``.
"""

import re

_KEY_RE = re.compile(r'\s+(\S+?)(?::\d+)?\s*[=:]?\s*"')


def build_loc_yml(existing_text, focuses, country_tag, *, language="english"):
    """Return ``(new_text, added_count)`` for the focus-tree loc .yml.

    ``existing_text`` is the current file contents, or ``None`` if the file
    doesn't exist yet (distinct from an existing-but-empty file, which still
    gets appended to rather than re-headered). ``focuses`` contributes a
    title-cased name key and a ``_desc`` key per focus (falling back to a
    generated sentence when the focus has no ``desc``). ``country_tag`` names
    the section header. Returns ``(None, 0)`` when every key is already
    present in ``existing_text`` — the caller should skip the write.
    """
    existing_keys = set()
    if existing_text is not None:
        for line in existing_text.splitlines():
            m = _KEY_RE.match(line)
            if m:
                existing_keys.add(m.group(1))

    new_loc = {}
    for f in focuses:
        title = f.name.replace("_", " ").title()
        desc = f.desc if f.desc else f"Complete the {title} national focus."
        new_loc[f.name] = title
        new_loc[f"{f.name}_desc"] = desc

    to_add = {k: v for k, v in new_loc.items() if k not in existing_keys}
    if not to_add:
        return None, 0

    base = existing_text if existing_text is not None else f"l_{language}:\n"
    needs_header = f"##########Focuses - {country_tag}##########" not in base
    addition = []
    if needs_header:
        addition.append(f"\n ##########Focuses - {country_tag}##########\n")
    for k, v in to_add.items():
        addition.append(f' {k}: "{v}"\n')
    return base + "".join(addition), len(to_add)
