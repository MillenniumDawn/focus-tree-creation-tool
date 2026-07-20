"""Canonical focus body rendering and Code-tab application."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Literal

from hoi4cm.models import Focus
from hoi4cm.script.effects import render_effect
from hoi4cm.script.syntax import serialize_block

from .build import build_focuses
from .parse import parse_focus_tree

__all__ = ["apply_focus_code", "render_focus_block", "render_focus_body"]

EffectRenderer = Callable[[Mapping[str, object]], str]
CoordinatePolicy = Literal["canvas", "raw"]
CompletionRewardPolicy = Literal["main", "extra", "preview"]
_DEFAULT_GFX = "GFX_goal_generic_political_pressure"

_EDITABLE_FIELDS = (
    "name",
    "gfx",
    "x",
    "y",
    "cost",
    "effects",
    "prereqs",
    "mutex",
    "cancel_if_invalid",
    "continue_if_invalid",
    "available_if_capitulated",
    "ai_will_do",
    "ai_will_do_raw",
    "relative_position_id",
    "search_filters",
    "available_cond",
    "bypass_cond",
    "cancel_cond",
    "will_lead_to_war_with",
    "complete_tooltip",
    "select_effect",
    "bypass_effect",
    "allow_branch",
    "text",
    "offsets",
)
_PRESERVED_PARSE_FIELDS = (
    "_raw_gx",
    "_raw_gy",
    "_rel_dx",
    "_rel_dy",
    "_joint_extra",
    "_script_extras",
)


def _emit_preserved_block(
    out: list[str], key: str, text: str, indent: str, inner_indent: str
) -> None:
    text = (text or "").strip()
    if not text:
        return
    out.append(f"{indent}{key} = {{")
    lines = text.splitlines()
    non_empty = [line for line in lines if line.strip()]
    min_indent = (
        min(len(line) - len(line.lstrip("\t")) for line in non_empty)
        if non_empty
        else 0
    )
    for line in lines:
        stripped = line[min_indent:] if len(line) >= min_indent else line.lstrip("\t")
        out.append(f"{inner_indent}{stripped}")
    out.append(f"{indent}}}")


def _emit_block(out: list[str], key: str, text: str, indent: str) -> None:
    text = text.strip()
    if not text:
        return
    out.append(f"{indent}{key} = {{")
    out.extend(
        f"{indent}\t{line.strip()}" for line in text.splitlines() if line.strip()
    )
    out.append(f"{indent}}}")


def _render_coordinates(
    focus: Focus,
    name_lookup: Mapping[str, Focus],
    *,
    policy: CoordinatePolicy,
) -> tuple[int, int, str | None]:
    if policy == "raw":
        x = getattr(focus, "_raw_gx", focus.x)
        y = getattr(focus, "_raw_gy", focus.y)
    else:
        x, y = focus.x, focus.y

    relative_id = getattr(focus, "relative_position_id", None)
    parent = name_lookup.get(relative_id) if relative_id else None
    if parent is None:
        return x, y, None

    if policy == "raw":
        dx = getattr(focus, "_rel_dx", None)
        dy = getattr(focus, "_rel_dy", None)
        if dx is None or dy is None:
            dx, dy = x - parent.x, y - parent.y
    else:
        dx, dy = x - parent.x, y - parent.y
    return dx, dy, relative_id


def _reindent_effect(text: str, indent: str) -> str:
    source_indent = "\t\t\t"
    return "\n".join(
        (
            f"{indent}{line[len(source_indent):]}"
            if line.startswith(source_indent)
            else line
        )
        for line in text.splitlines()
    )


def render_focus_body(
    focus: Focus,
    *,
    focus_lookup: Mapping[int, Focus],
    focus_name_lookup: Mapping[str, Focus],
    indent: str,
    effect_renderer: EffectRenderer = render_effect,
    coordinate_policy: CoordinatePolicy = "canvas",
    completion_reward_policy: CompletionRewardPolicy = "main",
    include_joint_extra: bool = False,
) -> list[str]:
    """Render fields after a focus's ``id`` and ``icon`` lines."""
    out: list[str] = []
    inner_indent = indent + "\t"
    text = getattr(focus, "text", "").strip()
    if text:
        out.append(f"{indent}text = {text}")

    x, y, relative_id = _render_coordinates(
        focus, focus_name_lookup, policy=coordinate_policy
    )
    out.extend((f"{indent}x = {x}", f"{indent}y = {y}"))
    if relative_id:
        out.append(f"{indent}relative_position_id = {relative_id}")

    for offset in getattr(focus, "offsets", []):
        out.extend(
            (
                f"{indent}offset = {{",
                f"{inner_indent}x = {offset['x']}",
                f"{inner_indent}y = {offset['y']}",
            )
        )
        trigger = offset.get("trigger", "").strip()
        if trigger:
            out.append(f"{inner_indent}trigger = {{")
            out.extend(
                f"{inner_indent}\t{line.strip()}" for line in trigger.splitlines()
            )
            out.append(f"{inner_indent}}}")
        out.append(f"{indent}}}")

    extras = getattr(focus, "_script_extras", None)
    if extras:
        rendered_extras = serialize_block(
            extras, indent=indent, include_bare_values=True, strip_strings=True
        )
        if rendered_extras:
            out.extend(rendered_extras.splitlines())

    out.append(f"{indent}cost = {focus.cost}")
    if include_joint_extra:
        joint_extra = getattr(focus, "_joint_extra", "").strip()
        out.extend(f"{indent}{line}" for line in joint_extra.splitlines())

    for group in focus.prereqs:
        valid = [focus_id for focus_id in group if focus_id in focus_lookup]
        if valid:
            values = " ".join(
                f"focus = {focus_lookup[focus_id].name}" for focus_id in valid
            )
            out.append(f"{indent}prerequisite = {{ {values} }}")
    for focus_id in focus.mutex:
        if focus_id in focus_lookup:
            out.append(
                f"{indent}mutually_exclusive = "
                f"{{ focus = {focus_lookup[focus_id].name} }}"
            )

    search_filters = getattr(focus, "search_filters", "").strip()
    if search_filters:
        out.append(f"{indent}search_filters = {{ {search_filters} }}")
    _emit_preserved_block(
        out, "allow_branch", getattr(focus, "allow_branch", ""), indent, inner_indent
    )
    for key, attribute in (
        ("available", "available_cond"),
        ("bypass", "bypass_cond"),
        ("cancel", "cancel_cond"),
    ):
        _emit_preserved_block(
            out, key, getattr(focus, attribute, ""), indent, inner_indent
        )

    war_target = getattr(focus, "will_lead_to_war_with", "").strip()
    if war_target:
        out.append(f"{indent}will_lead_to_war_with = {war_target}")
    _emit_block(out, "complete_tooltip", getattr(focus, "complete_tooltip", ""), indent)
    _emit_block(out, "select_effect", getattr(focus, "select_effect", ""), indent)
    if not focus.cancel_if_invalid:
        out.append(f"{indent}cancel_if_invalid = no")
    if focus.continue_if_invalid:
        out.append(f"{indent}continue_if_invalid = yes")
    if focus.available_if_capitulated:
        out.append(f"{indent}available_if_capitulated = yes")

    out.extend(("", f"{indent}completion_reward = {{"))
    has_raw_reward = bool(
        focus.effects
        and any(effect.get("type") == "_raw_block" for effect in focus.effects)
    )
    if completion_reward_policy == "main" and not has_raw_reward:
        out.append(
            f'{inner_indent}log = "[GetDateText]: [Root.GetName]: Focus {focus.name}"'
        )
    if focus.effects:
        out.extend(
            _reindent_effect(effect_renderer(effect), inner_indent)
            for effect in focus.effects
        )
    elif completion_reward_policy == "main":
        out.append(f"{inner_indent}# TODO: add effects")
    elif completion_reward_policy == "extra":
        out.extend(
            (
                f'{inner_indent}log = "[GetDateText]: [This.GetName]: '
                f'focus {focus.name} executed"',
                f"{inner_indent}# TODO: add effects",
            )
        )
    else:
        out.append(f"{inner_indent}# add effects here")
    out.append(f"{indent}}}")
    _emit_block(out, "bypass_effect", getattr(focus, "bypass_effect", ""), indent)

    out.extend(("", f"{indent}ai_will_do = {{"))
    raw_ai = getattr(focus, "ai_will_do_raw", "").strip()
    if raw_ai:
        out.extend(f"{inner_indent}{line.strip()}" for line in raw_ai.splitlines())
    else:
        out.append(f"{inner_indent}base = {focus.ai_will_do}")
    out.append(f"{indent}}}")
    return out


def render_focus_block(
    focus: Focus,
    *,
    focus_lookup: Mapping[int, Focus],
    focus_name_lookup: Mapping[str, Focus],
    effect_renderer: EffectRenderer = render_effect,
) -> str:
    """Render the editable Code-tab block for one focus."""
    indent = "\t\t"
    out = [
        "focus = {",
        f"{indent}id = {focus.name}",
        f"{indent}icon = {getattr(focus, 'gfx', _DEFAULT_GFX)}",
    ]
    out.extend(
        render_focus_body(
            focus,
            focus_lookup=focus_lookup,
            focus_name_lookup=focus_name_lookup,
            indent=indent,
            effect_renderer=effect_renderer,
            completion_reward_policy="preview",
            include_joint_extra=True,
        )
    )
    out.append("}")
    return "\n".join(out)


def apply_focus_code(
    focus: Focus,
    code: str,
    *,
    focus_lookup: Mapping[int, Focus],
    country_tag: str = "",
) -> None:
    """Validate Code-tab text and atomically update an existing focus."""
    parsed = parse_focus_tree(code, "code_tab_focus.txt")
    if len(parsed.focuses_data) != 1:
        raise ValueError("Code tab must contain exactly one focus block")

    existing = [
        candidate for candidate in focus_lookup.values() if candidate is not focus
    ]
    candidate = build_focuses(
        parsed,
        focus.tree_idx,
        country_tag=country_tag,
        existing_focuses=existing,
    )[0]
    candidate.prereqs = [
        [focus.id if value == candidate.id else value for value in group]
        for group in candidate.prereqs
    ]
    candidate.mutex = [
        focus.id if value == candidate.id else value for value in candidate.mutex
    ]
    for field in _EDITABLE_FIELDS:
        value = getattr(candidate, field, None)
        if isinstance(value, str):
            setattr(candidate, field, value.strip())
    for effect in candidate.effects:
        raw = effect.get("fields", {}).get("raw")
        if isinstance(raw, str):
            effect["fields"]["raw"] = raw.strip()
    for offset in candidate.offsets:
        offset["trigger"] = offset.get("trigger", "").strip()

    _preserve_raw_coordinates(focus, candidate, focus_lookup)

    values = {
        field: deepcopy(getattr(candidate, field))
        for field in (*_EDITABLE_FIELDS, *_PRESERVED_PARSE_FIELDS)
        if hasattr(candidate, field)
    }
    for field in _PRESERVED_PARSE_FIELDS:
        if field not in values and hasattr(focus, field):
            delattr(focus, field)
    for field, value in values.items():
        setattr(focus, field, value)


def _preserve_raw_coordinates(
    focus: Focus, candidate: Focus, focus_lookup: Mapping[int, Focus]
) -> None:
    if not hasattr(focus, "_raw_gx") or candidate.offsets != focus.offsets:
        return

    focus_by_name = {item.name: item for item in focus_lookup.values()}
    original_parent = focus_by_name.get(getattr(focus, "relative_position_id", ""))
    if original_parent is None:
        offset_x = focus.x - focus._raw_gx
        offset_y = focus.y - focus._raw_gy
    else:
        raw_dx = getattr(focus, "_rel_dx", focus._raw_gx)
        raw_dy = getattr(focus, "_rel_dy", focus._raw_gy)
        offset_x = focus.x - original_parent.x - raw_dx
        offset_y = focus.y - original_parent.y - raw_dy

    candidate_parent = focus_by_name.get(candidate.relative_position_id)
    if candidate_parent is None:
        candidate._raw_gx = candidate.x - offset_x
        candidate._raw_gy = candidate.y - offset_y
        return

    candidate._rel_dx = candidate.x - candidate_parent.x - offset_x
    candidate._rel_dy = candidate.y - candidate_parent.y - offset_y
    candidate._raw_gx = candidate._rel_dx
    candidate._raw_gy = candidate._rel_dy
