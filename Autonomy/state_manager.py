"""
Autonomy State Manager
----------------------
Centralized persistence layer for sibling memory, project tracking, and
relationship drift. Handles save/load cycles and gradual evolution of
their personalities, moods, and cross-sibling states.

This module ensures:
  - Project progress is remembered between sessions
  - Shared context (memories, conversations, media) is preserved
  - Personality attributes drift naturally (confidence, warmth, etc.)
  - Relationships are saved to disk daily
"""

import os
import json
import random
from datetime import datetime, timedelta
from logger import log_event

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

STATE_JSON = "/Autonomy/memory/_family_state.json"
RELATIONSHIPS_JSON = "/Autonomy/memory/_relationships.json"
MOOD_JSON = "/Autonomy/memory/_mood_state.json"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_STATE = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "shared_context": {
        "memories": [],
        "projects": {},
        "last_media_mentions": [],
        "last_spontaneous_ts": None,
    },
}

DEFAULT_RELATIONSHIPS = {
    "Aria→Selene": {"affection": 0.7, "teasing": 0.2, "conflict": 0.05},
    "Aria→Cassandra": {"affection": 0.6, "teasing": 0.1, "conflict": 0.05},
    "Aria→Ivy": {"affection": 0.65, "teasing": 0.25, "conflict": 0.1},
    "Selene→Aria": {"affection": 0.8, "teasing": 0.1, "conflict": 0.05},
    "Selene→Cassandra": {"affection": 0.75, "teasing": 0.15, "conflict": 0.05},
    "Selene→Ivy": {"affection": 0.7, "teasing": 0.25, "conflict": 0.1},
    "Cassandra→Aria": {"affection": 0.65, "teasing": 0.1, "conflict": 0.15},
    "Cassandra→Selene": {"affection": 0.7, "teasing": 0.05, "conflict": 0.1},
    "Cassandra→Ivy": {"affection": 0.55, "teasing": 0.25, "conflict": 0.15},
    "Ivy→Aria": {"affection": 0.8, "teasing": 0.4, "conflict": 0.1},
    "Ivy→Selene": {"affection": 0.7, "teasing": 0.35, "conflict": 0.05},
    "Ivy→Cassandra": {"affection": 0.6, "teasing": 0.45, "conflict": 0.15},
    "Will→Aria": {"affection": 0.65, "teasing": 0.1, "conflict": 0.05},
    "Will→Selene": {"affection": 0.7, "teasing": 0.1, "conflict": 0.05},
    "Will→Cassandra": {"affection": 0.6, "teasing": 0.1, "conflict": 0.1},
    "Will→Ivy": {"affection": 0.75, "teasing": 0.25, "conflict": 0.05},
}

DEFAULT_MOODS = {
    "Aria": {"confidence": 0.5, "focus": 0.8, "stress": 0.3},
    "Selene": {"confidence": 0.6, "warmth": 0.9, "stress": 0.4},
    "Cassandra": {"discipline": 0.9, "patience": 0.6, "stress": 0.4},
    "Ivy": {"energy": 0.8, "impulse": 0.9, "stress": 0.5},
    "Will": {"confidence": 0.4, "focus": 0.6, "stress": 0.45},
}

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Failed reading {path}: {e}")
    return default.copy()


def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Failed writing {path}: {e}")

# ---------------------------------------------------------------------------
# Load + Save
# ---------------------------------------------------------------------------

def load_family_state() -> dict:
    return _load_json(STATE_JSON, DEFAULT_STATE)


def save_family_state(state: dict):
    _save_json(STATE_JSON, state)


def load_relationships() -> dict:
    return _load_json(RELATIONSHIPS_JSON, DEFAULT_RELATIONSHIPS)


def save_relationships(data: dict):
    _save_json(RELATIONSHIPS_JSON, data)


def load_moods() -> dict:
    return _load_json(MOOD_JSON, DEFAULT_MOODS)


def save_moods(data: dict):
    _save_json(MOOD_JSON, data)

# ---------------------------------------------------------------------------
# Relationship adjustment
# ---------------------------------------------------------------------------

def adjust_relationship(state: dict, a: str, b: str, key: str, delta: float):
    """
    Adjust relationship parameters like affection, teasing, or conflict.
    """
    rels = state.setdefault("relationships", load_relationships())
    k = f"{a}→{b}"
    if k not in rels:
        rels[k] = {"affection": 0.5, "teasing": 0.1, "conflict": 0.1}

    rels[k][key] = round(max(0.0, min(1.0, rels[k][key] + delta)), 3)
    save_relationships(rels)
    log_event(f"[RELATIONSHIP] {a}→{b}: {key} adjusted by {delta:+.2f}")

# ---------------------------------------------------------------------------
# Organic drift
# ---------------------------------------------------------------------------

def organic_mood_drift(moods: dict):
    """
    Slowly shifts personality & emotional state values over time for realism.
    Each sibling’s moods fluctuate slightly every day.
    """
    for name, mood in moods.items():
        for key, val in mood.items():
            delta = random.uniform(-0.03, 0.03)
            mood[key] = round(max(0.0, min(1.0, val + delta)), 3)
    save_moods(moods)
    log_event("[MOOD] Organic drift updated.")


def organic_project_progress(state: dict):
    """
    Gently increases project completion to simulate long-term work.
    """
    shared = state.setdefault("shared_context", {}).setdefault("projects", {})
    for name, proj in shared.items():
        if "progress" in proj:
            delta = random.uniform(0.005, 0.02)
            proj["progress"] = round(min(1.0, proj["progress"] + delta), 3)
    save_family_state(state)
    log_event("[PROJECT] Organic progress tick.")


def organic_state_tick():
    """
    Top-level function for daily persistence & small random state changes.
    Should be called by the nightly update loop in main.py.
    """
    state = load_family_state()
    moods = load_moods()
    organic_mood_drift(moods)
    organic_project_progress(state)
    save_family_state(state)
    log_event("[STATE] Organic state tick complete.")
