# self_update.py
import os
import json
from datetime import datetime
from logger import log_event

UPDATES_DIR = "data/updates"
REFINEMENTS_LOG_DIR = "data/refinements"

# Ensure directories exist
os.makedirs(UPDATES_DIR, exist_ok=True)
os.makedirs(REFINEMENTS_LOG_DIR, exist_ok=True)


def _update_file_path(name: str) -> str:
    return os.path.join(UPDATES_DIR, f"{name}_updates.json")


def _log_file_path(name: str) -> str:
    return os.path.join(REFINEMENTS_LOG_DIR, f"{name}_log.txt")


# ---------------- Queueing ----------------
def queue_update(name: str, update: dict):
    """Save a requested or organic update to the update queue."""
    path = _update_file_path(name)
    updates = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                updates = json.load(f)
        except Exception:
            updates = []

    updates.append({
        "timestamp": datetime.now().isoformat(),
        "update": update,
    })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(updates, f, indent=2)

    log_event(f"[UPDATE QUEUED] {name}: {update}")


# ---------------- Application ----------------
def apply_updates_if_sleeping(name: str, state: dict, config: dict, profile_path: str):
    """Apply queued updates if the bot is asleep."""
    from sisters_behavior import get_today_rotation, is_awake
    lead = get_today_rotation(state, config)["lead"]

    sister_cfg = next((s for s in config["rotation"] if s["name"] == name), None)
    if not sister_cfg:
        return

    if is_awake(sister_cfg, lead):
        return  # Awake → defer updates

    path = _update_file_path(name)
    if not os.path.exists(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            updates = json.load(f)
    except Exception:
        updates = []

    if not updates:
        return

    # Load profile (or create baseline)
    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile_text = f.read()
        except Exception:
            profile_text = ""
    else:
        profile_text = ""

    applied = []
    for entry in updates:
        upd = entry.get("update", {})
        if "personality_shift" in upd:
            profile_text += f"\n[Shift {entry['timestamp']}]: {upd['personality_shift']}"
        if "behavior" in upd:
            profile_text += f"\n[Behavior {entry['timestamp']}]: {upd['behavior']}"
        if "schedule" in upd:
            profile_text += f"\n[Schedule {entry['timestamp']}]: {upd['schedule']}"

        applied.append(upd)

    # Write back updated profile
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(profile_text)

    # Append to refinements log
    with open(_log_file_path(name), "a", encoding="utf-8") as f:
        for upd in applied:
            f.write(f"{datetime.now().isoformat()} | {json.dumps(upd)}\n")

    # Clear queue after applying
    os.remove(path)
    log_event(f"[UPDATES APPLIED] {name}: {applied}")


# ---------------- Organic Update Rules ----------------
def generate_organic_updates(config: dict, state: dict) -> dict:
    """Return a dictionary of possible organic updates for each sibling."""
    return {
        "Aria": [
            {"personality_shift": "Becomes softer when Cassandra is stricter"},
            {"personality_shift": "More reflective when Ivy is being bratty"},
        ],
        "Selene": [
            {"personality_shift": "Acts more motherly when Will is shy"},
            {"personality_shift": "Becomes protective when Aria withdraws"},
        ],
        "Cassandra": [
            {"personality_shift": "Gets stricter when Ivy pushes boundaries"},
            {"personality_shift": "Softens slightly when Selene comforts her"},
        ],
        "Ivy": [
            {"personality_shift": "Brattier when ignored"},
            {"personality_shift": "Affectionate when Will retreats"},
        ],
        "Will": [
            {"personality_shift": "Bursts of outgoing energy"},
            {"personality_shift": "Quick to retreat if overwhelmed"},
        ],
    }
