"""Build the localisation .yml text for exported focuses.

Pure string building: no file I/O. The caller reads the existing loc file (if
any) and writes the result back; see ``hoi4_content_maker.py``'s ``_export``.
"""

import json
import re
from dataclasses import dataclass

_KEY_RE = re.compile(
    r'^(?P<prefix>\s+(?P<key>\S+?)(?::\d+)?\s*[=:]?\s*")'
    r'(?P<value>(?:[^"\\]|\\.)*)'
    r'(?P<suffix>".*)$',
    re.MULTILINE,
)


@dataclass(frozen=True)
class _LocSpec:
    display_name: str
    header_name: str
    directory: str
    filename_suffix: str


_LOC_SPECS = {
    "english": _LocSpec("English", "l_english", "english", "l_english"),
    "french": _LocSpec("French", "l_french", "french", "l_french"),
    "german": _LocSpec("German", "l_german", "german", "l_german"),
    "spanish": _LocSpec("Spanish", "l_spanish", "spanish", "l_spanish"),
    "braz_por": _LocSpec(
        "Brazilian Portuguese", "l_braz_por", "braz_por", "l_braz_por"
    ),
    "polish": _LocSpec("Polish", "l_polish", "polish", "l_polish"),
    "russian": _LocSpec("Russian", "l_russian", "russian", "l_russian"),
    "japanese": _LocSpec("Japanese", "l_japanese", "japanese", "l_japanese"),
    "simp_chinese": _LocSpec(
        "Simplified Chinese",
        "l_simp_chinese",
        "simp_chinese",
        "l_simp_chinese",
    ),
}

LOC_LANGUAGE_NAMES = {
    language: spec.display_name for language, spec in _LOC_SPECS.items()
}


@dataclass(frozen=True)
class LocTarget:
    """Resolve HOI4 localisation headers, directories, and filenames."""

    language: str = "english"

    def __post_init__(self):
        language = str(self.language or "").strip().lower()
        if language not in _LOC_SPECS:
            language = "english"
        object.__setattr__(self, "language", language)

    @property
    def display_name(self):
        return _LOC_SPECS[self.language].display_name

    def header(self):
        return f"{_LOC_SPECS[self.language].header_name}:"

    def dirname(self):
        return _LOC_SPECS[self.language].directory

    def filename(self, stem):
        return f"{stem}_{_LOC_SPECS[self.language].filename_suffix}.yml"


def build_loc_yml(existing_text, focuses, country_tag, *, language="english"):
    """Return ``(new_text, changed_count)`` for the focus-tree loc .yml.

    ``existing_text`` is the current file contents, or ``None`` if the file
    doesn't exist yet (distinct from an existing-but-empty file, which still
    gets appended to rather than re-headered). ``focuses`` contributes a
    title-cased name key and a ``_desc`` key per focus (falling back to a
    generated sentence when the focus has no ``desc``). ``country_tag`` names
    the section header.

    A missing key is appended. An existing ``_desc`` key is rewritten in
    place when the focus has a non-empty ``desc`` that differs from the
    value already on that line — a blank ``desc`` never overwrites a hand
    edit. Title keys (the bare focus name) are never rewritten. Returns
    ``(None, 0)`` when nothing needs to change — the caller should skip the
    write.
    """
    existing_values = {}
    if existing_text is not None:
        for m in _KEY_RE.finditer(existing_text):
            existing_values[m.group("key")] = m.group("value")

    to_add = {}
    to_update = {}
    for f in focuses:
        title = f.name.replace("_", " ").title()
        desc = f.desc if f.desc else f"Complete the {title} national focus."
        if f.name not in existing_values:
            to_add[f.name] = title

        desc_key = f"{f.name}_desc"
        if desc_key not in existing_values:
            to_add[desc_key] = desc
        elif f.desc:
            escaped = json.dumps(f.desc, ensure_ascii=False)[1:-1]
            if existing_values[desc_key] != escaped:
                to_update[desc_key] = f.desc

    if not to_add and not to_update:
        return None, 0

    target = LocTarget(language)
    base = existing_text if existing_text is not None else target.header() + "\n"
    if base and not base.endswith("\n"):
        base += "\n"

    if to_update:

        def _rewrite(m):
            key = m.group("key")
            if key not in to_update:
                return m.group(0)
            new_value = json.dumps(to_update[key], ensure_ascii=False)[1:-1]
            return m.group("prefix") + new_value + m.group("suffix")

        base = _KEY_RE.sub(_rewrite, base)

    needs_header = f"##########Focuses - {country_tag}##########" not in base
    addition = []
    if needs_header:
        addition.append(f"\n ##########Focuses - {country_tag}##########\n")
    for k, v in to_add.items():
        addition.append(f" {k}: {json.dumps(v, ensure_ascii=False)}\n")
    return base + "".join(addition), len(to_add) + len(to_update)
