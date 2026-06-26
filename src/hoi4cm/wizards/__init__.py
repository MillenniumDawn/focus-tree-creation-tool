"""HOI4 Content Maker wizards.

Each top-level wizard function (national spirit, decision, dyn-mod,
additional income, event) lives in its own submodule. The original
monolith had these as module-level functions; they were extracted here
to keep the launcher small and to make the per-wizard code easier to
test in isolation.
"""

from hoi4cm.wizards.additional_income import open_additional_income_wizard
from hoi4cm.wizards.decision import open_decision_wizard
from hoi4cm.wizards.dyn_mod import open_dyn_mod_wizard
from hoi4cm.wizards.event import open_event_wizard
from hoi4cm.wizards.national_spirit import open_national_spirit_wizard

__all__ = [
    "open_national_spirit_wizard",
    "open_decision_wizard",
    "open_dyn_mod_wizard",
    "open_additional_income_wizard",
    "open_event_wizard",
]
