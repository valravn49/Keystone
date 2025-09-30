import os
import json
import random
from datetime import datetime
from logger import log_event

# ---------------- Queue & Apply ----------------
UPDATE_QUEUE = {}

def queue_update(name: str, update: dict):
    """Queue a behavior/personality update for a sibling."""
    q = UPDATE_QUEUE.setdefault(name, [])
    q.append(update)
    log_event(f"[UPDATE-QUEUED] {name}: {update}")

def _is_sleeping(state, name: str, config: dict) -> bool:
    """Rough awake/sleep check: sisters by wake/bed in config, Will by schedule."""
    now_hour = datetime.now().hour
    if name == "Will":
        sc = state.get("will_schedule")
        if not sc:
            return True
        wake, sleep = sc["wake"], sc["sleep"]
        if wake < sleep:
            return not (wake <= now_hour < sleep)
        return not (now_hour >= wake or now_hour < sleep)
    else:
        sister_cfg = next((s for s in config["rotation"] if s["name"] == name), {})
        wake = int(sister_cfg.get("wake", "6:00").split(":")[0])
        bed = int(sister_cfg.get("bed", "22:00").split(":")[0])
        if wake < bed:
            return not (wake <= now_hour < bed)
        return not (now_hour >= wake or now_hour < bed)

def _persist_update_to_profile(name: str, update: dict):
    """Append update to that sibling’s profile text file (best-effort)."""
    path = f"data/{name}_Profile.txt"
    try:
        os.makedirs("data", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n# {datetime.now().isoformat()} UPDATE\n{json.dumps(update)}\n")
    except Exception as e:
        log_event(f"[ERROR] Persist {name}: {e}")

def apply_updates_if_sleeping(name: str, state, config, profile_path: str = None):
    """Apply queued updates if sibling is sleeping."""
    if not _is_sleeping(state, name, config):
        return
    updates = UPDATE_QUEUE.pop(name, [])
    if not updates:
        return
    for upd in updates:
        log_event(f"[UPDATE-APPLIED] {name}: {upd}")
        if profile_path:
            _persist_update_to_profile(name, upd)

# ---------------- Organic drift ----------------
def generate_organic_updates(config, state):
    """
    Create organic update candidates for each sibling.
    Called nightly by main.py.
    """
    updates = {}
    for s in config["rotation"]:
        n = s["name"]
        updates[n] = []
        if n == "Aria":
            if random.random() < 0.5:
                updates[n].append({"behavior": "Speak less about books; more about present feelings and siblings."})
        elif n == "Selene":
            if random.random() < 0.5:
                updates[n].append({"behavior": "Tone shifts to gentler, indulgent responses today."})
            else:
                updates[n].append({"behavior": "Tone steadies; pragmatic and thoughtful."})
        elif n == "Cassandra":
            if random.random() < 0.5:
                updates[n].append({"behavior": "Softens slightly; still firm but warmer in tone."})
            else:
                updates[n].append({"behavior": "Doubles down on discipline; sharper tone today."})
        elif n == "Ivy":
            if random.random() < 0.5:
                updates[n].append({"behavior": "Brattiness more extreme today."})
            else:
                updates[n].append({"behavior": "Affection more extreme today."})
    # Will separately
    updates["Will"] = []
    if random.random() < 0.5:
        updates["Will"].append({"behavior": "More timid; quieter and hesitant."})
    else:
        updates["Will"].append({"behavior": "Outgoing burst potential today, but quicker to retreat if flustered."})
    return updates
