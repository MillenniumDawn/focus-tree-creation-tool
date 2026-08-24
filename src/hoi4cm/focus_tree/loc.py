"""Build the localisation .yml text for exported focuses.

Pure string building: no file I/O. The caller reads the existing loc file (if
any) and writes the result back; see ``hoi4_content_maker.py``'s ``_export``.
"""

import json
import re
from dataclasses import dataclass

_KEY_RE = re.compile(r'\s+(\S+?)(?::\d+)?\s*[=:]?\s*"')


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

    target = LocTarget(language)
    base = existing_text if existing_text is not None else target.header() + "\n"
    if base and not base.endswith("\n"):
        base += "\n"
    needs_header = f"##########Focuses - {country_tag}##########" not in base
    addition = []
    if needs_header:
        addition.append(f"\n ##########Focuses - {country_tag}##########\n")
    for k, v in to_add.items():
        addition.append(f" {k}: {json.dumps(v, ensure_ascii=False)}\n")
    return base + "".join(addition), len(to_add)
