# /app/self_update.py
"""
Nightly self-update system (Option A):
- Evolves BOTH Personality JSONs and Memory JSONs in small organic increments.
- Applies queued user updates if the bot is sleeping.
- Introduces moods, drift in likes/dislikes (slow), and project progress.
- Adds small inter-sibling relational nudges via memory notes.
"""

import os
import json
import random
from datetime import datetime

from logger import log_event

# Where JSONs live
PERS_PATH = "/mnt/data/{name}_Personality.json"
MEMO_PATH = "/mnt/data/{name}_Memory.json"

# Queue in-memory
_UPDATE_QUEUE = {}  # {name: [dict, ...]}

# --------- IO helpers ---------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] self_update read failed {path}: {e}")
    return default

def _save_json(path: str, data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] self_update write failed {path}: {e}")

def _persona(name: str) -> dict:
    return _load_json(PERS_PATH.format(name=name), {
        "name": name, "likes": [], "dislikes": [], "style": [], "interests": [],
        "triggers": [], "favorites": [], "mood_today": "neutral"
    })

def _memo(name: str) -> dict:
    return _load_json(MEMO_PATH.format(name=name), {
        "projects": {}, "recent_notes": [], "last_outfit_prompt": None
    })

def _save_persona(name: str, data: dict) -> None:
    _save_json(PERS_PATH.format(name=name), data)

def _save_memo(name: str, data: dict) -> None:
    _save_json(MEMO_PATH.format(name=name), data)

# --------- Public API ---------
def queue_update(name: str, update: dict):
    """Add a structured update to apply while sleeping."""
    _UPDATE_QUEUE.setdefault(name, []).append(update)

def apply_updates_if_sleeping(name: str, state: dict, config: dict, profile_path_ignored: str | None = None):
    """
    Applies queued updates and organic drift if the bot is within its sleep window.
    profile_path_ignored kept for backward compatibility with older callers.
    """
    sched = _assign_today_schedule(name, state, config)
    now_h = datetime.now().hour
    if _hour_in_range(now_h, sched["wake"], sched["sleep"]):
        # awake → skip; we only mutate during sleep
        return

    # Personality + memory
    p = _persona(name)
    m = _memo(name)

    # Apply queued updates
    for upd in _UPDATE_QUEUE.pop(name, []):
        # Generic fields
        if "likes_add" in upd:
            for v in upd["likes_add"]:
                if v not in p.setdefault("likes", []):
                    p["likes"].append(v)
        if "dislikes_add" in upd:
            for v in upd["dislikes_add"]:
                if v not in p.setdefault("dislikes", []):
                    p["dislikes"].append(v)
        if "behavior" in upd:
            # log-only semantic change; mood/tone shift handled below
            m["recent_notes"].append(f"[behavior note] {upd['behavior']}")
        if "personality_shift" in upd:
            m["recent_notes"].append(f"[personality shift] {upd['personality_shift']}")
        if "project_nudge" in upd:
            title = upd["project_nudge"].get("title", "Personal task")
            delta = upd["project_nudge"].get("delta", 0.05)
            pj = m.setdefault("projects", {}).setdefault(title, {"progress": 0.0, "note": "n/a"})
            pj["progress"] = round(max(0.0, min(1.0, pj["progress"] + delta)), 2)

    # Organic drift (small)
    _organic_mood_shift(p)
    _organic_likes_drift(p)
    _organic_project_progress(m)

    # Save
    _save_persona(name, p)
    _save_memo(name, m)
    log_event(f"[SELF-UPDATE] Applied nightly updates for {name}")

def generate_organic_updates(config: dict, state: dict) -> dict:
    """
    Suggest small per-sibling organic updates. Caller may choose to queue some of these.
    Returns: {name: [update_dict, ...]}
    """
    updates = {}
    for s in config.get("rotation", []):
        name = s["name"]
        arr = []

        # Small chance add a new like from what siblings mention commonly
        common_like = random.choice([
            "making playlists", "late-night walks", "loose cardigans", "lavender tea",
            "cozy game streams", "tidy desks", "weekend batch-cooking"
        ])
        if random.random() < 0.25:
            arr.append({"likes_add": [common_like]})

        # Small project nudge
        if random.random() < 0.45:
            arr.append({"project_nudge": {"title": _seed_title(name), "delta": round(random.uniform(0.03, 0.10), 2)}})

        if arr:
            updates[name] = arr

    # Will too
    arr = []
    if random.random() < 0.35:
        arr.append({"likes_add": [random.choice(["indie pixel art", "mini mechanical keyboards", "cozy hoodie outfits"]) ]})
    if random.random() < 0.5:
        arr.append({"project_nudge": {"title": "Small coding experiment", "delta": round(random.uniform(0.03, 0.10), 2)}})
    if arr:
        updates["Will"] = arr

    return updates

# --------- Internals ---------
def _seed_title(name: str) -> str:
    seeds = {
        "Aria": "Weekly planner revamp",
        "Selene": "Comfort-food recipe cards",
        "Cassandra": "Shelf re-organization",
        "Ivy": "Closet restyle challenge",
        "Will": "Small coding experiment",
    }
    return seeds.get(name, "Personal task")

def _organic_mood_shift(p: dict):
    # 15% chance of a notable mood; else neutral variants
    mood_pool = ["neutral", "neutral", "calm", "focused", "tired", "light", "playful"]
    if random.random() < 0.15:
        mood_pool += ["snappy", "quiet", "clingy"]  # small dramatic spice
    p["mood_today"] = random.choice(mood_pool)

def _organic_likes_drift(p: dict):
    # Tiny drift — adopt at most one new adjacent like, remove rarely
    if random.random() < 0.20:
        candidates = ["calm playlists", "weekly resets", "shared cooking", "cozy knits", "organizing drawers"]
        cand = random.choice(candidates)
        if cand not in p.setdefault("likes", []):
            p["likes"].append(cand)
    if p.get("likes") and random.random() < 0.05:
        # soft removal chance
        removed = random.choice(p["likes"])
        p["likes"].remove(removed)

def _organic_project_progress(m: dict):
    for title, pj in m.setdefault("projects", {}).items():
        delta = random.uniform(0.01, 0.06)
        pj["progress"] = round(max(0.0, min(1.0, pj.get("progress", 0.0) + delta)), 2)
        pj["updated"] = datetime.now().isoformat(timespec="seconds")

# Schedule helpers (mirror of behavior modules)
def _assign_today_schedule(name: str, state: dict, config: dict):
    key = f"{name}_schedule"
    kd = f"{key}_date"
    today = datetime.now().date()
    if state.get(kd) == today and key in state:
        return state[key]
    sch = (config.get("schedules", {}) or {}).get(name, {"wake": [6,8], "sleep":[22,23]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        return random.randint(lo, hi) if hi >= lo else lo
    out = {"wake": pick(sch.get("wake",[6,8])), "sleep": pick(sch.get("sleep",[22,23]))}
    state[key] = out
    state[kd] = today
    return out

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep: return True
    if wake < sleep: return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep
