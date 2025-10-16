"""
Autonomy package initializer.

Handles high-level imports for the sibling autonomy system.
This module intentionally avoids circular imports by referencing
only the active components — behavior modules, self-update, and utilities.
"""

# ─────────────────────────────────────────────
# Imports for active modules
# ─────────────────────────────────────────────
# from .autonomy import AutonomyEngine  # core runtime (if used)
# from .state_manager import state  # shared persistent state handler
# from .self_update import queue_update, apply_updates_if_sleeping, generate_organic_updates

# ─────────────────────────────────────────────
# Behavior modules (new structure)
# ─────────────────────────────────────────────
from .behaviors.aria_behavior import *    # noqa
from .behaviors.selene_behavior import *  # noqa
from .behaviors.cassandra_behavior import *  # noqa
from .behaviors.ivy_behavior import *     # noqa
from .behaviors.will_behavior import *    # noqa

# ─────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────
__all__ = [
    "AutonomyEngine",
    "state",
    "queue_update",
    "apply_updates_if_sleeping",
    "generate_organic_updates",
]
