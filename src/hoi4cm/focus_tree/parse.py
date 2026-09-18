"""Focus-tree script parsing — text in, structured data out.

Pure functions: no tkinter, no globals, no file I/O. The caller reads the file
and hands the raw text to :func:`parse_focus_tree`, which returns a
:class:`ParsedFocusTree`. Building :class:`~hoi4cm.models.Focus` objects from
that data lives in :mod:`hoi4cm.focus_tree.build`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from hoi4cm.script.syntax import (
    match_brace,
    parse_block,
    serialize_block,
    strip_comments,
    tokenize,
)

# Keep malformed nested files from repeatedly rescanning the same suffix.
MAX_RAW_BLOCK_RESCANS = 4_096
MAX_RAW_BLOCK_RESCAN_CHARS = 8_000_000

# Conditional/effect blocks preserved verbatim from a focus block.
_COND_KEYS = (
    "available",
    "bypass",
    "cancel",
    "will_lead_to_war_with",
    "complete_tooltip",
    "select_effect",
    "bypass_effect",
    "allow_branch",
)

# focus_tree = { ... } wrapper keys already captured by named ParsedFocusTree
# fields. Anything else (default, reset_on_civilwar, initial_show_position,
# ...) is preserved verbatim in tree_extras so it survives a round-trip.
_KNOWN_TREE_FIELDS = frozenset(
    {
        "id",
        "continuous_focus_position",
        "country",
        "focus",
        "shared_focus",
        "joint_focus",
    }
)


class EmptyFocusTreeError(ValueError):
    """Raised when a focus-tree file holds no recognizable focus data.

    Subclasses ``ValueError`` so existing ``except ValueError`` / ``except
    Exception`` callers keep working. The message carries the detailed
    "blocks found" diagnostic.
    """


class FocusTreeParseCancelled(Exception):
    """Raised when parsing is cancelled before a complete model is built."""


class FocusTreeParseBudgetExceeded(ValueError):
    """Raised when bounded raw-block rescanning reaches its limit."""


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
    country_raw: str = ""
    tree_extras: dict = field(default_factory=dict)


# Every raw block pulled verbatim off a single focus block, in one alternation
# so the scan happens once instead of once per key. Deliberately unanchored,
# matching what the per-key ``re.search`` below does: a key preceded by other
# identifier characters still counts, and the regex backtracks into the longer
# alternatives, so ``bypass_effect = {`` matches as itself and not as
# ``bypass``.
_RAW_KEYS = ("completion_reward", *_COND_KEYS, "joint_trigger")
_RAW_KEY_RE = re.compile(rf"(?P<key>{'|'.join(_RAW_KEYS)})\s*=\s*\{{")


def _dedent_raw_block(source, start, end):
    """Return ``source[start + 1:end]`` with its common tab indent removed."""
    lines = source[start + 1 : end].split("\n")
    min_indent = min(
        (len(ln) - len(ln.lstrip("\t")) for ln in lines if ln and not ln.isspace()),
        default=0,
    )
    if min_indent:  # a zero-indent (or all-blank) block needs no re-slicing
        lines = [ln[min_indent:] if len(ln) >= min_indent else ln for ln in lines]
    return "\n".join(lines).strip("\n")


def _check_cancelled(cancelled):
    if cancelled is None:
        return
    requested = cancelled() if callable(cancelled) else cancelled.is_set()
    if requested:
        raise FocusTreeParseCancelled


@dataclass
class _RawRescanBudget:
    scans: int = 0
    chars: int = 0
    exhausted: bool = False

    def match(self, source, start):
        if self.exhausted:
            return None
        if (
            self.scans >= MAX_RAW_BLOCK_RESCANS
            or self.chars >= MAX_RAW_BLOCK_RESCAN_CHARS
        ):
            self.exhausted = True
            return None
        remaining = MAX_RAW_BLOCK_RESCAN_CHARS - self.chars
        if len(source) - start > remaining + 1:
            end = match_brace(source, start, start + remaining + 1)
        else:
            end = match_brace(source, start)
        cost = max(0, end - start)
        self.scans += 1
        self.chars += cost
        if self.chars > MAX_RAW_BLOCK_RESCAN_CHARS:
            self.exhausted = True
            return None
        return end


def _scan_brace(source, start, cancelled=None, budget=None):
    _check_cancelled(cancelled)
    end = match_brace(source, start) if budget is None else budget.match(source, start)
    _check_cancelled(cancelled)
    return end


def extract_raw_block(source, key, cancelled=None, budget=None):
    """Return the dedented inner text of ``key = { ... }`` in ``source``."""
    m = re.search(key + r"\s*=\s*\{", source)
    if not m:
        return ""
    start = m.end() - 1
    end = _scan_brace(source, start, cancelled, budget)
    if end is None or end >= len(source):
        return ""
    return _dedent_raw_block(source, start, end)


def _extract_raw_key_blocks(source, cancelled=None, budget=None):
    """Return ``{key: dedented inner}`` for the first hit of each raw key.

    One pass over the focus block replaces eleven independent
    :func:`extract_raw_block` calls, most of which find nothing and pay a full
    scan of the block to say so.
    """
    found = {}
    for match in _RAW_KEY_RE.finditer(source):
        key = match.group("key")
        if key in found:  # first hit wins, as a per-key ``re.search`` would
            continue
        start = match.end() - 1
        end = _scan_brace(source, start, cancelled, budget)
        if end is None:
            break
        found[key] = "" if end >= len(source) else _dedent_raw_block(source, start, end)
        if len(found) == len(_RAW_KEYS):
            break
    return {key: text for key, text in found.items() if text}


_FOCUS_BLOCK_RE = re.compile(r"\b(?:shared_focus|joint_focus|focus)\s*=\s*\{")


def focus_block_starts(txt):
    """Return the ``{`` index of every ``focus``/``shared_focus`` block."""
    return [m.end() - 1 for m in _FOCUS_BLOCK_RE.finditer(txt)]


def block_to_str(block, depth=1):
    """Convert a parsed block dict back to HOI4 script text.

    Handles nested dicts, repeated keys (lists), and bools (True->yes).
    """
    if not block:
        return ""
    return serialize_block(block, indent="\t" * depth, strip_strings=True)


def _extract_raw_rewards(txt, block_starts=None, cancelled=None, budget=None):
    """Pull verbatim reward/condition/offset blocks keyed by focus id.

    ``block_starts`` are the ``{`` indices of every focus block, from
    :data:`_FOCUS_BLOCK_RE`; :func:`parse_focus_tree` scans for them once and
    shares the list with its own two passes.
    """
    raw_rewards = {}
    if block_starts is None:
        block_starts = focus_block_starts(txt)
    if budget is None:
        budget = _RawRescanBudget()
    for fs in block_starts:
        _check_cancelled(cancelled)
        block_end = _scan_brace(txt, fs, cancelled, budget)
        if block_end is None:
            break
        fblock = txt[fs + 1 : block_end]
        id_m = re.search(r"\bid\s*=\s*(\S+)", fblock)
        if not id_m:
            continue
        fid = id_m.group(1)
        blocks = _extract_raw_key_blocks(fblock, cancelled, budget)
        reward = blocks.get("completion_reward")
        if reward:
            raw_rewards[fid] = reward
        for ck in _COND_KEYS:
            cv = blocks.get(ck)
            if cv:
                raw_rewards[(fid, ck)] = cv
        # offset = { x = N y = M trigger = { ... } } blocks as structured data
        offsets = []
        for om in re.finditer(r"\boffset\s*=\s*\{", fblock):
            _check_cancelled(cancelled)
            os_ = om.end() - 1
            offset_end = _scan_brace(fblock, os_, cancelled, budget)
            if offset_end is None:
                break
            oinner = fblock[os_ + 1 : offset_end]
            oxm = re.search(r"\bx\s*=\s*(-?\d+)", oinner)
            oym = re.search(r"\by\s*=\s*(-?\d+)", oinner)
            ox = int(oxm.group(1)) if oxm else 0
            oy = int(oym.group(1)) if oym else 0
            otrig = extract_raw_block(oinner, "trigger", cancelled, budget)
            offsets.append({"x": ox, "y": oy, "trigger": otrig})
        if offsets:
            raw_rewards[(fid, "_offsets")] = offsets
        # joint_trigger preserved as extra raw text (offset stored separately)
        jt = blocks.get("joint_trigger")
        if jt:
            raw_rewards[(fid, "_joint_extra")] = f"joint_trigger = {{\n{jt}\n}}"
        _check_cancelled(cancelled)
    return raw_rewards


def _raise_if_budget_exhausted(path, budget, block_count=None):
    if budget.exhausted or (
        block_count is not None and block_count > MAX_RAW_BLOCK_RESCANS
    ):
        raise FocusTreeParseBudgetExceeded(
            f"Focus tree parse budget exhausted in {os.path.basename(path)} "
            f"(limit: {MAX_RAW_BLOCK_RESCANS:,} block scans or "
            f"{MAX_RAW_BLOCK_RESCAN_CHARS:,} characters)"
        )


def parse_focus_tree(raw, path, cancelled=None):
    """Parse focus-tree script text into a :class:`ParsedFocusTree`.

    ``path`` is used only to derive the default tree name and for diagnostics.
    Raises :class:`EmptyFocusTreeError` when no focus blocks are found and
    :class:`FocusTreeParseBudgetExceeded` when bounded rescanning is exhausted.
    """
    _check_cancelled(cancelled)
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    txt = strip_comments(raw)
    _check_cancelled(cancelled)
    shared_refs = re.findall(r"\bshared_focus\s*=\s*([^\s{]\S*)", txt)
    joint_refs = re.findall(r"\bjoint_focus\s*=\s*([^\s{]\S*)", txt)

    block_starts = focus_block_starts(txt)
    rescan_budget = _RawRescanBudget()
    _raise_if_budget_exhausted(path, rescan_budget, len(block_starts))
    raw_rewards = _extract_raw_rewards(txt, block_starts, cancelled, rescan_budget)
    _check_cancelled(cancelled)
    _raise_if_budget_exhausted(path, rescan_budget)

    tokens = tokenize(txt)
    _check_cancelled(cancelled)
    focuses_data = []
    tree_name = os.path.splitext(os.path.basename(path))[0]
    cfp_x = cfp_y = None
    country_tag = "TAG"
    country_raw = ""
    tree_extras: dict = {}
    wrapper_seen = False

    def parse_or_reject(block_tokens, position):
        _check_cancelled(cancelled)
        try:
            block, next_position = parse_block(block_tokens, position)
        except RecursionError as exc:
            raise EmptyFocusTreeError(
                f"Focus tree nesting too deep in {os.path.basename(path)}"
            ) from exc
        _check_cancelled(cancelled)
        return block, next_position

    i = 0
    while i < len(tokens):
        _check_cancelled(cancelled)
        if tokens[i] == "focus_tree" and i + 1 < len(tokens) and tokens[i + 1] == "=":
            wrapper_seen = True
            block, i = parse_or_reject(tokens, i + 2)
            _id_val = block.get("id")
            if isinstance(_id_val, str):
                tree_name = _id_val
            cfp_blk = block.get("continuous_focus_position", {})
            if isinstance(cfp_blk, dict):
                try:
                    cfp_x = int(cfp_blk.get("x", ""))
                except ValueError, TypeError:
                    cfp_x = None
                try:
                    cfp_y = int(cfp_blk.get("y", ""))
                except ValueError, TypeError:
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
                    if tag and len(tag) >= 2:
                        country_tag = tag
            # Preserve the full country block verbatim so it can be written
            # back unchanged on export.
            country_raw = extract_raw_block(txt, "country", cancelled, rescan_budget)
            _raise_if_budget_exhausted(path, rescan_budget)
            tree_extras = {
                key: value
                for key, value in block.items()
                if key not in _KNOWN_TREE_FIELDS
            }
            _raw_focuses = block.get("focus", [])
            if isinstance(_raw_focuses, dict):
                raw_focuses: list[object] = [_raw_focuses]
            elif isinstance(_raw_focuses, list):
                raw_focuses = _raw_focuses
            else:
                raw_focuses = []
            for rf in raw_focuses:
                if isinstance(rf, dict):
                    focuses_data.append(rf)
        else:
            i += 1

    had_wrapper = wrapper_seen  # True if a focus_tree = { } wrapper was parsed

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
                blk, i = parse_or_reject(tokens, i + 2)
                if isinstance(blk, dict) and "id" in blk:
                    focuses_data.append(blk)
            else:
                i += 1

    # Robust per-focus fallback: HOI4's own parser tolerates structural quirks
    # (an unbalanced brace, malformed `key=val={...}` patterns, etc.) that the
    # structured/bare passes above can choke on. Walk the raw text, brace-match
    # each `focus = { ... }` / `shared_focus = { ... }` block, and parse each
    # one independently. If this finds more focuses than already collected,
    # prefer it.
    #
    # The fallback can find at most one focus per `focus = {` block, so when
    # the passes above already produced that many it can never win — skip the
    # brace-walk entirely on well-formed files (the common case).
    if len(focuses_data) < len(block_starts) and not rescan_budget.exhausted:
        per_block_focuses = []
        fallback_complete = True
        for bs in block_starts:  # each is the index of a block's '{'
            _check_cancelled(cancelled)
            bi = _scan_brace(txt, bs, cancelled, rescan_budget)
            _raise_if_budget_exhausted(path, rescan_budget)
            if bi is None:
                fallback_complete = False
                break
            if bi >= len(txt):
                continue
            btxt = txt[bs : bi + 1]
            _check_cancelled(cancelled)
            btoks = tokenize(btxt)
            if not btoks or btoks[0] != "{":
                continue
            bdict, _ = parse_or_reject(btoks, 0)
            _check_cancelled(cancelled)
            if isinstance(bdict, dict) and "id" in bdict:
                per_block_focuses.append(bdict)
        if fallback_complete and len(per_block_focuses) > len(focuses_data):
            focuses_data = per_block_focuses

    _raise_if_budget_exhausted(path, rescan_budget)

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
        country_raw=country_raw,
        tree_extras=tree_extras,
    )
