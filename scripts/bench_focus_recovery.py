#!/usr/bin/env python3
"""Bounded public-fixture recovery/scene benchmark; no GUI required.

Run this same script with --repo BASELINE and --repo PATCHED. Fixture reads warm
OS caches naturally; no claim of cold filesystem caches. Timing and tracemalloc
are separate. Writes go only into the supplied output directory.
"""

# ruff: noqa: E402
# pylint: disable=wrong-import-position
import argparse
import gc
import json
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--focus-dir", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--samples", type=int, default=5)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / "src"))
from hoi4cm.editor.project_codec import encode_project, write_project
from hoi4cm.focus_tree.batch_load import batch_load_trees
from hoi4cm.models import EditorWorkspace, FocusDocument, TreeDocument, TreeMetadata
from hoi4cm.ui.scene_index import SceneIndex

try:
    from hoi4cm.editor.autosave_writer import AutosaveWriter
except ImportError:
    AutosaveWriter = None  # type: ignore[misc,assignment]

args.out.mkdir(parents=True, exist_ok=True)
files = sorted(args.focus_dir.rglob("*.txt"))
rows, _ = batch_load_trees(
    [(str(p), "shared") for p in files], [], 0, "", lambda *_: None
)
workspace = EditorWorkspace(
    focuses=FocusDocument([f for row in rows if row["ok"] for f in row["new_focuses"]]),
    extra_trees=[
        TreeDocument(
            metadata=TreeMetadata(tree_id=row["parsed"].tree_id),
            tree_type=row["type"],
            file_path=str(Path(row["path"]).relative_to(args.focus_dir)),
            focus_ids={f.id for f in row["new_focuses"]},
        )
        for row in rows
        if row["ok"]
    ],
)
paths = tuple(str(args.out / name) for name in ("global.json", "sibling.json"))
writer = AutosaveWriter() if AutosaveWriter is not None else None


def save():
    if writer:
        writer.save(
            workspace, paths, lambda: (_ for _ in ()).throw(RuntimeError("sibling"))
        )
    else:
        for path in paths:
            write_project(path, workspace)


def sample(function):
    values = []
    for _ in range(args.samples):
        gc.collect()
        start = time.perf_counter()
        function()
        values.append((time.perf_counter() - start) * 1000)
    return {"ms": values, "median_ms": statistics.median(values)}


def changed_save():
    workspace.focuses.touch()
    save()


report = {
    "head": subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True
    ).strip(),
    "python": sys.version,
    "focuses": len(workspace.focuses),
    "files": len(files),
    "rejected": [row["path"] for row in rows if not row["ok"]],
    "changed_recovery_pair": sample(changed_save),
    "unchanged_recovery_pair": sample(save),
    "scene_rebuild": sample(lambda: SceneIndex().rebuild(workspace.focuses)),
}
assert Path(paths[0]).read_bytes() == Path(paths[1]).read_bytes()
assert json.loads(Path(paths[0]).read_text(encoding="utf-8")) == encode_project(
    workspace
)
tracemalloc.start()
changed_save()
report["separate_tracemalloc_peak_bytes"] = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()
report["recovery_outputs_equal"] = True
(args.out / "measurements.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8"
)
print(json.dumps(report, indent=2))
