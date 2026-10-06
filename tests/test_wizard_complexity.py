"""Fixed C901 budgets for the intentionally monolithic wizard closures."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Function-level complexity scores when the ratchet was added. This fixed list
# is a cap, not a generated snapshot: lowering scores is allowed, growth and new
# C901 findings fail. Keep C901 selected only for the wizard tree in this test.
WIZARD_COMPLEXITY_BUDGETS = {
    "src/hoi4cm/wizards/_generators.py:render_event_txt": 14,
    "src/hoi4cm/wizards/_generators.py:generate_decision_block": 53,
    "src/hoi4cm/wizards/_generators.py:build_dyn_mod_output": 16,
    "src/hoi4cm/wizards/_generators.py:build_national_spirit_output": 26,
    "src/hoi4cm/wizards/_generators.py:generate_decision_categories_file": 13,
    "src/hoi4cm/wizards/_shared.py:open_script_picker": 34,
    "src/hoi4cm/wizards/additional_income.py:open_additional_income_wizard": 26,
    "src/hoi4cm/wizards/additional_income.py:_apply": 15,
    "src/hoi4cm/wizards/decision.py:open_decision_wizard": 560,
    "src/hoi4cm/wizards/decision.py:_rebuild_tree": 18,
    "src/hoi4cm/wizards/decision.py:_collect": 24,
    "src/hoi4cm/wizards/decision.py:_build_dec_editor": 47,
    "src/hoi4cm/wizards/decision.py:_rebuild_tgt": 16,
    "src/hoi4cm/wizards/decision.py:_populate_dec_editor": 14,
    "src/hoi4cm/wizards/decision.py:_decode_dec_icon": 14,
    "src/hoi4cm/wizards/decision.py:_decode_cat_picture": 14,
    "src/hoi4cm/wizards/decision.py:_hoi4_loc_widget": 15,
    "src/hoi4cm/wizards/decision.py:_build_preview": 34,
    "src/hoi4cm/wizards/decision.py:_build_code": 52,
    "src/hoi4cm/wizards/decision.py:_apply_code_edits": 34,
    "src/hoi4cm/wizards/decision.py:_browse_mod_decisions": 14,
    "src/hoi4cm/wizards/decision.py:_import_txt": 70,
    "src/hoi4cm/wizards/decision.py:_import_scripted_loc": 13,
    "src/hoi4cm/wizards/decision.py:_import_yml_loc": 13,
    "src/hoi4cm/wizards/decision.py:_save_to_mod": 33,
    "src/hoi4cm/wizards/dyn_mod.py:open_dyn_mod_wizard": 175,
    "src/hoi4cm/wizards/dyn_mod.py:_open_dynmod_gfx_browser": 42,
    "src/hoi4cm/wizards/dyn_mod.py:_dm_save_raw": 31,
    "src/hoi4cm/wizards/dyn_mod.py:_save_file": 48,
    "src/hoi4cm/wizards/dyn_mod.py:_browse_mod_dynmods": 29,
    "src/hoi4cm/wizards/dyn_mod.py:_load_selected": 18,
    "src/hoi4cm/wizards/event.py:open_event_wizard": 269,
    "src/hoi4cm/wizards/event.py:_render_preview": 27,
    "src/hoi4cm/wizards/event.py:_decode_preview_image": 12,
    "src/hoi4cm/wizards/event.py:_save_to_mod": 35,
    "src/hoi4cm/wizards/event.py:_browse_mod_events": 11,
    "src/hoi4cm/wizards/event.py:_import_txt": 19,
    "src/hoi4cm/wizards/event.py:_open_event_gfx_browser": 44,
    "src/hoi4cm/wizards/event.py:_update_gfx_compat": 11,
    "src/hoi4cm/wizards/national_spirit.py:open_national_spirit_wizard": 204,
    "src/hoi4cm/wizards/national_spirit.py:_open_idea_gfx_browser": 37,
    "src/hoi4cm/wizards/national_spirit.py:_save_raw": 47,
    "src/hoi4cm/wizards/national_spirit.py:_save_to_mod": 29,
    "src/hoi4cm/wizards/national_spirit.py:_browse_existing_spirits": 35,
    "src/hoi4cm/wizards/national_spirit.py:_load_selected": 15,
}


def test_wizard_c901_has_fixed_function_budgets():
    ruff = Path(sys.executable).with_name("ruff.exe" if os.name == "nt" else "ruff")
    executable = str(ruff) if ruff.is_file() else shutil.which("ruff")
    assert executable is not None, "Ruff is required for the wizard complexity ratchet"

    result = subprocess.run(
        [
            executable,
            "check",
            "--select",
            "C901",
            "--output-format",
            "json",
            "src/hoi4cm/wizards",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode in (0, 1), result.stderr

    observed = {}
    pattern = re.compile(r"`([^`]+)` is too complex \((\d+) > 10\)")
    for finding in json.loads(result.stdout):
        if finding["code"] != "C901":
            continue
        source = Path(finding["filename"]).resolve().relative_to(ROOT).as_posix()
        match = pattern.fullmatch(finding["message"])
        assert match is not None, finding["message"]
        key = f"{source}:{match.group(1)}"
        assert key not in observed, f"duplicate C901 finding for {key}"
        observed[key] = int(match.group(2))

    assert observed, "Ruff reported no C901 findings for the wizard tree"
    new_findings = sorted(observed.keys() - WIZARD_COMPLEXITY_BUDGETS.keys())
    growth = {
        key: (WIZARD_COMPLEXITY_BUDGETS[key], score)
        for key, score in observed.items()
        if key in WIZARD_COMPLEXITY_BUDGETS and score > WIZARD_COMPLEXITY_BUDGETS[key]
    }
    assert not new_findings, f"new complex wizard functions: {new_findings}"
    assert not growth, f"wizard functions exceeded fixed C901 budgets: {growth}"


def test_complexity_budget_covers_the_existing_wizard_baseline():
    assert len(WIZARD_COMPLEXITY_BUDGETS) == 45
