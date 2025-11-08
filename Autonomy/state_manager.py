# Autonomy/state_manager.py
# Unified state persistence, rotation, and theme management.

import os
import json
from datetime import datetime, date
import pytz
from typing import Dict, Any

# ------------------------------------------------------------
# Constants
# ------------------------------------------------------------

STATE_FILE = os.environ.get("STATE_FILE", "/app/data/state.json")
AEDT = pytz.timezone("Australia/Sydney")

# ------------------------------------------------------------
# Global state dictionary
# ------------------------------------------------------------
state: Dict[str, Any] = {}

# ------------------------------------------------------------
# Core persistence
# ------------------------------------------------------------
def load_state() -> Dict[str, Any]:
    """Load persistent state from disk."""
    global state
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        else:
            state = {}
    except Exception as e:
        print(f"[WARN] Failed to load state: {e}")
        state = {}

    # Ensure essential keys exist
    state.setdefault("rotation_index", 0)
    state.setdefault("theme_index", 0)
    state.setdefault("last_theme_update", None)
    state.setdefault("morning_done", False)
    state.setdefault("night_done", False)

    return state


def save_state(state_dict: Dict[str, Any] = None):
    """Persist current state to disk."""
    global state
    if state_dict is not None:
        state = state_dict
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp_path = STATE_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_FILE)
    except Exception as e:
        print(f"[WARN] Failed to save state: {e}")

# ------------------------------------------------------------
# Rotation system
# ------------------------------------------------------------

def get_today_rotation(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns the current family role rotation:
    - lead: primary active sibling
    - rest: sibling taking downtime
    - supports: everyone else
    """
    rotation = config.get("rotation", [])
    if not rotation:
        rotation = [{"name": n} for n in ["Aria", "Selene", "Cassandra", "Ivy", "Will"]]

    idx = state.get("rotation_index", 0) % len(rotation)
    lead = rotation[idx]["name"]
    rest = rotation[(idx + 1) % len(rotation)]["name"]
    supports = [r["name"] for r in rotation if r["name"] not in [lead, rest]]

    return {"lead": lead, "rest": rest, "supports": supports}


def advance_rotation(state: Dict[str, Any], config: Dict[str, Any]) -> int:
    """
    Moves rotation forward by one step. Called after morning ritual.
    """
    total = len(config.get("rotation", [])) or 5
    new_index = (state.get("rotation_index", 0) + 1) % total
    state["rotation_index"] = new_index
    save_state(state)
    return new_index


# ------------------------------------------------------------
# Theme management
# ------------------------------------------------------------

def get_current_theme(state: Dict[str, Any], config: Dict[str, Any]) -> str:
    """
    Rotates weekly themes (on Mondays AEDT).
    """
    themes = config.get("themes", [
        "focus and balance",
        "creativity",
        "rest and renewal",
        "growth and reflection",
        "connection and warmth"
    ])

    today = date.today()
    last_update = state.get("last_theme_update")
    idx = state.get("theme_index", 0)

    if not last_update or (today.weekday() == 0 and last_update != str(today)):
        idx = (idx + 1) % len(themes)
        state["theme_index"] = idx
        state["last_theme_update"] = str(today)
        save_state(state)

    return themes[idx]


# ------------------------------------------------------------
# Daily reset flags
# ------------------------------------------------------------

def reset_daily_flags():
    """
    Resets morning/night flags when new day starts.
    """
    now = datetime.now(AEDT).date()
    last_reset = state.get("last_reset_date")
    if last_reset != str(now):
        state["morning_done"] = False
        state["night_done"] = False
        state["last_reset_date"] = str(now)
        save_state(state)

# ------------------------------------------------------------
# Utility
# ------------------------------------------------------------

def debug_state_summary() -> str:
    """Quick summary for logs or /health output."""
    rotation = state.get("rotation_index", 0)
    theme = state.get("theme_index", 0)
    morning = state.get("morning_done")
    night = state.get("night_done")
    return f"rotation={rotation}, theme={theme}, morning_done={morning}, night_done={night}"
