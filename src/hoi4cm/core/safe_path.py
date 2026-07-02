"""Path-safety helpers for untrusted filename components.

Mod files (focus trees, decisions, events, ...) are downloaded and shared, so
IDs and tags parsed out of them are untrusted. When such a value becomes part
of an output filename it must not be able to escape the target folder with a
``..`` segment or a path separator. Sanitize the component first, or use
``safe_join`` to verify the final path stays inside the intended base.
"""

import os
import re

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def sanitize_component(name, fallback="unnamed"):
    """Reduce *name* to a single safe path segment.

    Drops any directory prefix, replaces characters outside
    ``[A-Za-z0-9_.-]`` with ``_``, and rejects the traversal names
    ``""``/``.``/``..`` by returning *fallback*.
    """
    text = str(name).strip().replace("\\", "/")
    text = text.rsplit("/", 1)[-1]  # keep only the final segment
    text = _UNSAFE.sub("_", text)
    text = text.strip(". ")  # no leading/trailing dots or spaces
    if text in ("", ".", ".."):
        return fallback
    return text


def safe_join(base, *parts):
    """Join *parts* onto *base* and confirm the result stays within *base*.

    Raises ``ValueError`` if the resolved path escapes *base* — via ``..``, an
    absolute component, or a symlink.
    """
    base_real = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base_real, *parts))
    try:
        if os.path.commonpath([base_real, target]) != base_real:
            raise ValueError(f"path escapes base directory: {target!r}")
    except ValueError:
        # commonpath raises on different drives/roots — treat as an escape.
        raise ValueError(f"path escapes base directory: {target!r}") from None
    return target
