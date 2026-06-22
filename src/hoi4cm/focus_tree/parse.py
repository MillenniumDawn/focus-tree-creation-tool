"""Focus-tree script parsing — text in, structured data out.

Pure functions: no tkinter, no globals, no file I/O. The caller reads the file
and hands the raw text to :func:`parse_focus_tree`, which returns a
:class:`ParsedFocusTree`. Building :class:`~hoi4cm.models.Focus` objects from
that data lives in :mod:`hoi4cm.focus_tree.build`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Conditional/effect blocks preserved verbatim from a focus block.
_COND_KEYS = (
    "available",
    "bypass",
    "cancel",
    "will_lead_to_war_with",
    "complete_tooltip",
    "select_effect",
    "bypass_effect",
)


class EmptyFocusTreeError(ValueError):
    """Raised when a focus-tree file holds no recognizable focus data.

    Subclasses ``ValueError`` so existing ``except ValueError`` / ``except
    Exception`` callers keep working. The message carries the detailed
    "blocks found" diagnostic.
    """


@dataclass
class ParsedFocusTree:
    """Structured result of parsing one focus-tree file."""

    tree_id: str
    cfp_x: int | None
    cfp_y: int | None
    country_tag: str
    shared_refs: list
    joint_refs: list
    had_wrapper: bool
    focuses_data: list
    raw_rewards: dict


def strip_comments(s):
    """Drop ``#`` comments, keeping line structure."""
    return "\n".join(
        (line[: line.find("#")] if "#" in line else line) for line in s.splitlines()
    )


def extract_raw_block(source, key):
    """Return the dedented inner text of ``key = { ... }`` in ``source``."""
    m = re.search(key + r"\s*=\s*\{", source)
    if not m:
        return ""
    start = m.end() - 1
    depth = 0
    i = start
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                inner = source[start + 1 : i]
                lines = inner.split("\n")
                non_empty = [ln for ln in lines if ln.strip()]
                if non_empty:
                    min_indent = min(len(ln) - len(ln.lstrip("\t")) for ln in non_empty)
                    lines = [
                        ln[min_indent:] if len(ln) >= min_indent else ln for ln in lines
                    ]
                return "\n".join(lines).strip("\n")
        i += 1
    return ""


def tokenize(s):
    """Split HOI4 script into ``{`` ``}`` ``=`` and bareword/quoted tokens."""
    tokens = []
    i = 0
    while i < len(s):
        c = s[i]
        if c in " \t\n\r":
            i += 1
            continue
        if c == "{":
            tokens.append("{")
            i += 1
            continue
        if c == "}":
            tokens.append("}")
            i += 1
            continue
        if c == "=":
            tokens.append("=")
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < len(s) and s[j] != '"':
                j += 1
            tokens.append(s[i + 1 : j])
            i = j + 1
            continue
        j = i
        while j < len(s) and s[j] not in ' \t\n\r{}="':
            j += 1
        if j > i:
            tokens.append(s[i:j])
        i = j
    return tokens


def parse_block(tokens, pos):
    """Recursively parse a ``{ ... }`` block starting at ``tokens[pos]``.

    Repeated keys collapse into lists; bare words land in ``_values``.
    Returns ``(dict, next_pos)``.
    """
    result = {}
    pos += 1
    while pos < len(tokens) and tokens[pos] != "}":
        key = tokens[pos]
        pos += 1
        if pos >= len(tokens):
            break
        if tokens[pos] == "=":
            pos += 1
            if pos >= len(tokens):
                break
            if tokens[pos] == "{":
                val, pos = parse_block(tokens, pos)
            else:
                val = tokens[pos]
                pos += 1
            if key in result:
                existing = result[key]
                if not isinstance(existing, list):
                    result[key] = [existing]
                result[key].append(val)
            else:
                result[key] = val
        else:
            if key not in ("", "=", "{", "}"):
                result.setdefault("_values", []).append(key)
    return result, pos + 1


def block_to_str(block, depth=1):
    """Convert a parsed block dict back to HOI4 script text.

    Handles nested dicts, repeated keys (lists), and bools (True->yes).
    """
    if not block:
        return ""
    if isinstance(block, bool):
        return "yes" if block else "no"
    if isinstance(block, str):
        return block.strip()
    if not isinstance(block, dict):
        return str(block)
    indent = "\t" * depth
    lines = []
    for k, v in block.items():
        if str(k).startswith("_"):
            continue
        if isinstance(v, bool):
            lines.append(f"{indent}{k} = {'yes' if v else 'no'}")
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    inner = block_to_str(item, depth + 1)
                    lines.append(f"{indent}{k} = {{\n{inner}\n{indent}}}")
                elif isinstance(item, bool):
                    lines.append(f"{indent}{k} = {'yes' if item else 'no'}")
                else:
                    lines.append(f"{indent}{k} = {item}")
        elif isinstance(v, dict):
            inner = block_to_str(v, depth + 1)
            lines.append(f"{indent}{k} = {{\n{inner}\n{indent}}}")
        else:
            lines.append(f"{indent}{k} = {v}")
    return "\n".join(lines)


def _extract_raw_rewards(txt):
    """Pull verbatim reward/condition/offset blocks keyed by focus id."""
    raw_rewards = {}
    for fm in re.finditer(r"\b(?:shared_focus|joint_focus|focus)\s*=\s*\{", txt):
        fs = fm.end() - 1
        depth = 0
        fi = fs
        while fi < len(txt):
            if txt[fi] == "{":
                depth += 1
            elif txt[fi] == "}":
                depth -= 1
                if depth == 0:
                    break
            fi += 1
        fblock = txt[fs + 1 : fi]
        id_m = re.search(r"\bid\s*=\s*(\S+)", fblock)
        if not id_m:
            continue
        fid = id_m.group(1)
        reward = extract_raw_block(fblock, "completion_reward")
        if reward:
            raw_rewards[fid] = reward
        for ck in _COND_KEYS:
            cv = extract_raw_block(fblock, ck)
            if cv:
                raw_rewards[(fid, ck)] = cv
        # offset = { x = N y = M trigger = { ... } } blocks as structured data
        offsets = []
        for om in re.finditer(r"\boffset\s*=\s*\{", fblock):
            os_ = om.end() - 1
            od = 0
            oi = os_
            while oi < len(fblock):
                if fblock[oi] == "{":
                    od += 1
                elif fblock[oi] == "}":
                    od -= 1
                    if od == 0:
                        break
                oi += 1
            oinner = fblock[os_ + 1 : oi]
            oxm = re.search(r"\bx\s*=\s*(-?\d+)", oinner)
            oym = re.search(r"\by\s*=\s*(-?\d+)", oinner)
            ox = int(oxm.group(1)) if oxm else 0
            oy = int(oym.group(1)) if oym else 0
            otrig = extract_raw_block(oinner, "trigger")
            offsets.append({"x": ox, "y": oy, "trigger": otrig})
        if offsets:
            raw_rewards[(fid, "_offsets")] = offsets
        # joint_trigger preserved as extra raw text (offset stored separately)
        jt = extract_raw_block(fblock, "joint_trigger")
        if jt:
            raw_rewards[(fid, "_joint_extra")] = f"joint_trigger = {{\n{jt}\n}}"
    return raw_rewards


def parse_focus_tree(raw, path):
    """Parse focus-tree script text into a :class:`ParsedFocusTree`.

    ``path`` is used only to derive the default tree name and for diagnostics.
    Raises :class:`EmptyFocusTreeError` when no focus blocks are found.
    """
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    txt = strip_comments(raw)
    shared_refs = re.findall(r"\bshared_focus\s*=\s*(\S+)", txt)
    joint_refs = re.findall(r"\bjoint_focus\s*=\s*(\S+)", txt)

    raw_rewards = _extract_raw_rewards(txt)

    tokens = tokenize(txt)
    focuses_data = []
    tree_name = os.path.splitext(os.path.basename(path))[0]
    cfp_x = cfp_y = None
    country_tag = "TAG"
    i = 0
    while i < len(tokens):
        if tokens[i] == "focus_tree" and i + 1 < len(tokens) and tokens[i + 1] == "=":
            block, i = parse_block(tokens, i + 2)
            tree_name = block.get("id", tree_name)
            cfp_blk = block.get("continuous_focus_position", {})
            if isinstance(cfp_blk, dict):
                try:
                    cfp_x = int(cfp_blk.get("x", ""))
                except Exception:
                    cfp_x = None
                try:
                    cfp_y = int(cfp_blk.get("y", ""))
                except Exception:
                    cfp_y = None
            country_blk = block.get("country", {})
            if isinstance(country_blk, dict):
                mod_blk = country_blk.get("modifier", {})
                if isinstance(mod_blk, dict):
                    tag = (
                        (mod_blk.get("original_tag") or mod_blk.get("tag") or "")
                        .upper()
                        .strip()
                    )
                    if tag:
                        country_tag = tag
            raw_focuses = block.get("focus", [])
            if isinstance(raw_focuses, dict):
                raw_focuses = [raw_focuses]
            for rf in raw_focuses:
                if isinstance(rf, dict):
                    focuses_data.append(rf)
        else:
            i += 1

    had_wrapper = bool(focuses_data)  # True if file had a focus_tree = { } wrapper

    # Fallback: top-level focus/shared_focus/joint_focus blocks (no wrapper).
    if not focuses_data:
        i = 0
        while i < len(tokens):
            if (
                tokens[i] in ("focus", "shared_focus", "joint_focus")
                and i + 1 < len(tokens)
                and tokens[i + 1] == "="
                and i + 2 < len(tokens)
                and tokens[i + 2] == "{"
            ):
                blk, i = parse_block(tokens, i + 2)
                if isinstance(blk, dict) and "id" in blk:
                    focuses_data.append(blk)
            else:
                i += 1

    if not focuses_data:
        found = [
            kw
            for kw in ("focus_tree", "focus", "shared_focus", "joint_focus")
            if re.search(rf"\b{kw}\s*=\s*\{{", txt)
        ]
        detail = (
            f"Blocks found: {', '.join(found)} — none had valid focus IDs."
            if found
            else "No recognized block types found."
        )
        raise EmptyFocusTreeError(
            f"No focus data found in {os.path.basename(path)}\n\n{detail}"
        )

    return ParsedFocusTree(
        tree_id=tree_name,
        cfp_x=cfp_x,
        cfp_y=cfp_y,
        country_tag=country_tag,
        shared_refs=shared_refs,
        joint_refs=joint_refs,
        had_wrapper=had_wrapper,
        focuses_data=focuses_data,
        raw_rewards=raw_rewards,
    )
