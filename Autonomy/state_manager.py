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
# Global state
# ------------------------------------------------------------
state: Dict[str, Any] = {}

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _json_safe(obj):
    """Convert unsupported objects to serializable types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

# ------------------------------------------------------------
# Load / Save
# ------------------------------------------------------------
def load_state() -> Dict[str, Any]:
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

    # Defaults
    state.setdefault("rotation_index", 0)
    state.setdefault("theme_index", 0)
    state.setdefault("last_theme_update", None)
    state.setdefault("morning_done", False)
    state.setdefault("night_done", False)
    state.setdefault("last_reset_date", None)
    return state


def save_state(state_dict: Dict[str, Any] = None):
    """Persist state safely to disk."""
    global state
    if state_dict is not None:
        state = state_dict
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=_json_safe)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        print(f"[WARN] Failed to save state: {e}")

# ------------------------------------------------------------
# Rotation
# ------------------------------------------------------------
def get_today_rotation(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    rotation = config.get("rotation", [])
    if not rotation:
        rotation = [{"name": n} for n in ["Aria", "Selene", "Cassandra", "Ivy", "Will"]]

    idx = state.get("rotation_index", 0) % len(rotation)
    lead = rotation[idx]["name"]
    rest = rotation[(idx + 1) % len(rotation)]["name"]
    supports = [r["name"] for r in rotation if r["name"] not in [lead, rest]]

    return {"lead": lead, "rest": rest, "supports": supports}


def advance_rotation(state: Dict[str, Any], config: Dict[str, Any]) -> int:
    total = len(config.get("rotation", [])) or 5
    new_index = (state.get("rotation_index", 0) + 1) % total
    state["rotation_index"] = new_index
    save_state(state)
    return new_index

# ------------------------------------------------------------
# Themes
# ------------------------------------------------------------
def get_current_theme(state: Dict[str, Any], config: Dict[str, Any]) -> str:
    themes = config.get("themes", [
        "focus and balance",
        "creativity",
        "rest and renewal",
        "growth and reflection",
        "connection and warmth",
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
# Daily reset
# ------------------------------------------------------------
def reset_daily_flags():
    now = datetime.now(AEDT).date()
    if state.get("last_reset_date") != str(now):
        state["morning_done"] = False
        state["night_done"] = False
        state["last_reset_date"] = str(now)
        save_state(state)

# ------------------------------------------------------------
# Debug summary
# ------------------------------------------------------------
def debug_state_summary() -> str:
    return (
        f"rotation={state.get('rotation_index')}, "
        f"theme={state.get('theme_index')}, "
        f"morning_done={state.get('morning_done')}, "
        f"night_done={state.get('night_done')}"
    )
