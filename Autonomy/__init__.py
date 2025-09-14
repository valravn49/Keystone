"""
Sister Autonomy System

This package manages:
- Personality state (loading, drift, persistence)
- Autonomy scheduling (random conversations, self-talk)
- DM handling (direct messages from user to sisters)
"""

from .personality import PersonalityManager
from .autonomy import AutonomyEngine
from .dm_handler import handle_dm
