"""Plan and run focus-tree exports without touching Tkinter or app state."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from hoi4cm.core.logger import get_logger
from hoi4cm.core.paths import read_file
from hoi4cm.mod.workspace_files import WriteEntry
from hoi4cm.models import Focus

from .export import export_focus_tree, export_main_tree
from .loc import build_loc_yml

_log = get_logger("export_plan")

WriteTexts = Callable[[Iterable[WriteEntry]], None]
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class ExportPlan:
    """Everything needed to render and write one focus tree."""

    label: str
    tree_type: str
    focus_path: str
    focuses: tuple[Focus, ...]
    tree_info: Mapping[str, object]
    focus_lookup: Mapping[int, Focus]
    focus_name_lookup: Mapping[str, Focus]
    loc_path: str | None = None
    extra_tree_idx: int | None = None


@dataclass(frozen=True)
class ExportResult:
    """The outcome of one export plan in a batch."""

    plan: ExportPlan
    written_paths: tuple[str, ...] = ()
    localisation_added: int = 0
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def make_main_export_plan(
    *,
    label: str,
    focus_path: str,
    loc_path: str,
    focuses: Iterable[Focus],
    tree_info: Mapping[str, object],
    focus_lookup: Mapping[int, Focus],
    focus_name_lookup: Mapping[str, Focus],
) -> ExportPlan:
    """Create a main-tree plan after the UI has resolved its destinations."""
    return ExportPlan(
        label=label,
        tree_type="main",
        focus_path=focus_path,
        loc_path=loc_path,
        focuses=tuple(focuses),
        tree_info=dict(tree_info),
        focus_lookup=dict(focus_lookup),
        focus_name_lookup=dict(focus_name_lookup),
    )


def make_extra_export_plan(
    *,
    label: str,
    focus_path: str,
    focuses: Iterable[Focus],
    tree_info: Mapping[str, object],
    focus_lookup: Mapping[int, Focus],
    focus_name_lookup: Mapping[str, Focus],
    extra_tree_idx: int,
) -> ExportPlan:
    """Create a shared/joint-tree plan after the UI has resolved its destination."""
    return ExportPlan(
        label=label,
        tree_type="extra",
        focus_path=focus_path,
        focuses=tuple(focuses),
        tree_info=dict(tree_info),
        focus_lookup=dict(focus_lookup),
        focus_name_lookup=dict(focus_name_lookup),
        extra_tree_idx=extra_tree_idx,
    )


def render_export_plan(
    plan: ExportPlan,
    *,
    read_text: Callable[[str], str] = read_file,
    is_file: Callable[[str], bool] = os.path.isfile,
) -> tuple[tuple[WriteEntry, ...], int]:
    """Render a plan into the atomic write group it needs."""
    if plan.tree_type == "main":
        out_text = export_main_tree(
            plan.focuses,
            plan.tree_info,
            focus_lookup=plan.focus_lookup,
            focus_name_lookup=plan.focus_name_lookup,
        )
        existing_loc_text = (
            read_text(plan.loc_path)
            if plan.loc_path is not None and is_file(plan.loc_path)
            else None
        )
        new_loc_text, added_count = build_loc_yml(
            existing_loc_text,
            plan.focuses,
            str(plan.tree_info["country_tag"]),
        )
        writes = [(plan.focus_path, out_text, "utf-8")]
        if new_loc_text is not None and plan.loc_path is not None:
            writes.append((plan.loc_path, new_loc_text, "utf-8-sig"))
        return tuple(writes), added_count

    out_text = export_focus_tree(
        plan.focuses,
        plan.tree_info,
        focus_lookup=plan.focus_lookup,
        focus_name_lookup=plan.focus_name_lookup,
    )
    return ((plan.focus_path, out_text, "utf-8"),), 0


def execute_export_plans(
    plans: Iterable[ExportPlan],
    write_texts: WriteTexts,
    *,
    progress: ProgressCallback | None = None,
    read_text: Callable[[str], str] = read_file,
    is_file: Callable[[str], bool] = os.path.isfile,
) -> list[ExportResult]:
    """Render and write each plan, continuing after individual failures."""
    queued = tuple(plans)
    total = len(queued)
    results = []
    for index, plan in enumerate(queued, start=1):
        if progress is not None:
            progress(index, total, plan.label)
        try:
            writes, added_count = render_export_plan(
                plan, read_text=read_text, is_file=is_file
            )
            write_texts(writes)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            _log.error("export failed for %s: %s", plan.label, error, exc_info=True)
            results.append(ExportResult(plan=plan, error=error))
        else:
            results.append(
                ExportResult(
                    plan=plan,
                    written_paths=tuple(str(path) for path, _text, _encoding in writes),
                    localisation_added=added_count,
                )
            )
    return results


__all__ = [
    "ExportPlan",
    "ExportResult",
    "execute_export_plans",
    "make_extra_export_plan",
    "make_main_export_plan",
    "render_export_plan",
]
