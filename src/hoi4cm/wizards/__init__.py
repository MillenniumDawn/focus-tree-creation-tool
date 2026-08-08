"""HOI4 Content Maker wizards.

Each top-level wizard function (national spirit, decision, dyn-mod,
additional income, event) lives in its own submodule. The original
monolith had these as module-level functions; they were extracted here
to keep the launcher small and to make the per-wizard code easier to
test in isolation.

Attribute access imports the owning submodule on demand. Importing them
all here instead would undo that: `ui/mod_loading.py` pulls `_shared` in
at module scope, so a launch that never opens a wizard would still pay
for all five (~12k lines between them).
"""

import importlib

_WIZARD_MODULES = {
    "open_national_spirit_wizard": "national_spirit",
    "open_decision_wizard": "decision",
    "open_dyn_mod_wizard": "dyn_mod",
    "open_additional_income_wizard": "additional_income",
    "open_event_wizard": "event",
}

__all__ = list(_WIZARD_MODULES)


def __getattr__(name):
    if name not in _WIZARD_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod = importlib.import_module(f".{_WIZARD_MODULES[name]}", __name__)
    value = getattr(mod, name)
    globals()[name] = value
    return value
