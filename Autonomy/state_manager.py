import os
import json
from datetime import datetime
from logger import log_event

# -------------------------------------------------------------------
# Persistent state file location
# -------------------------------------------------------------------
STATE_FILE = "/Autonomy/state.json"

# Default structure for all runtime data
DEFAULT_STATE = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "spontaneous_cooldowns": {},
    "shared_context": {
        "memories": [],
        "projects": {},
        "last_media_mentions": [],
        "last_spontaneous_ts": None,
        "convo_threads": {},
    },
}

# -------------------------------------------------------------------
# Global in-memory state
# -------------------------------------------------------------------
state = DEFAULT_STATE.copy()

# -------------------------------------------------------------------
# State Helpers
# -------------------------------------------------------------------
def load_state() -> dict:
    """Load persistent global state from disk, merging with defaults."""
    global state
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Merge saved data into defaults (non-destructive)
            merged = DEFAULT_STATE.copy()
            for k, v in data.items():
                if isinstance(v, dict) and k in merged:
                    merged[k].update(v)
                else:
                    merged[k] = v

            state.update(merged)
            log_event(f"[STATE] Loaded and merged from {STATE_FILE}")
        else:
            log_event("[STATE] No existing file found, using defaults.")
    except Exception as e:
        log_event(f"[ERROR] Failed to load state: {e}")
    return state


def save_state(current_state: dict = None):
    """Persist the current runtime state to disk."""
    global state
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(current_state or state, f, ensure_ascii=False, indent=2)
        log_event(f"[STATE] Saved successfully → {STATE_FILE}")
    except Exception as e:
        log_event(f"[ERROR] Failed to save state: {e}")


def reset_state():
    """Reset all state values to defaults and save immediately."""
    global state
    state = DEFAULT_STATE.copy()
    save_state(state)
    log_event("[STATE] Reset performed (defaults restored).")


# -------------------------------------------------------------------
# Auto-load at import
# -------------------------------------------------------------------
try:
    load_state()
except Exception as e:
    log_event(f"[WARN] State auto-load failed: {e}")
