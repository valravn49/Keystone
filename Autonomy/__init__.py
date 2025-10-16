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
from .self_update import queue_update, apply_updates_if_sleeping, generate_organic_updates

# ─────────────────────────────────────────────
# Behavior modules (new structure)
# ─────────────────────────────────────────────
from .behaviors.Aria_behavior import *    # noqa
from .behaviors.Selene_behavior import *  # noqa
from .behaviors.Cassandra_behavior import *  # noqa
from .behaviors.Ivy_behavior import *     # noqa
from .behaviors.Will_behavior import *    # noqa

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
