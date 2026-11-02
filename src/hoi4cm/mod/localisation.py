"""Raw title and description lookup for existing wizard content."""

import re

from hoi4cm.core.paths import read_file_with_encoding
from hoi4cm.mod.context import find_loc_files

_VALUE_RE = re.compile(r'^\s+(\S+?)(?::\d+)?\s+"(.*)"', re.MULTILINE)


def lookup_localisation(
    mod_root: str | None, identifier: str, *, language: str = "english"
) -> tuple[str, str]:
    """Return the first nonempty raw title and description in discovery order."""
    name = description = ""
    for path in find_loc_files(mod_root, language=language):
        try:
            source, _encoding = read_file_with_encoding(path)
            if source is None:
                continue
            for match in _VALUE_RE.finditer(source):
                key, value = match.group(1), match.group(2)
                if key == identifier and not name:
                    name = value
                elif key == f"{identifier}_desc" and not description:
                    description = value
            if name and description:
                break
        except OSError, ValueError, UnicodeDecodeError:
            pass
    return name, description
