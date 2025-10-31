import os
import json
import random
from datetime import datetime
from logger import log_event

# ---------------------------------------------------------------------------
# Base path and constants
# ---------------------------------------------------------------------------

MEMORY_BASE = "/Autonomy/memory"
SEASONAL_FILE = os.path.join(MEMORY_BASE, "Shared_Seasonal_Memory.json")
MAX_MEMORIES_PER_EVENT = 15  # cap for each event

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: str, default: dict) -> dict:
    """Safely load a JSON file."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] MemoryHelpers: Failed to load {path}: {e}")
    return default


def _save_json(path: str, data: dict):
    """Safely save a JSON file."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] MemoryHelpers: Failed to write {path}: {e}")

# ---------------------------------------------------------------------------
# Shared seasonal memory system
# ---------------------------------------------------------------------------

def add_seasonal_memory(sibling_name: str, event: str, note: str):
    """
    Add a short memory associated with a sibling and an event (e.g. 'Christmas').
    Stored in a single shared file so all siblings can recall the same history.
    """
    memory_data = _load_json(SEASONAL_FILE, {})
    event_key = event.lower()

    memories = memory_data.setdefault(event_key, [])
    timestamp = datetime.now().isoformat(timespec="seconds")
    entry = {"sibling": sibling_name, "note": note, "timestamp": timestamp}

    memories.append(entry)
    # Keep list short
    memory_data[event_key] = memories[-MAX_MEMORIES_PER_EVENT:]

    _save_json(SEASONAL_FILE, memory_data)
    log_event(f"[MEMORY] Added {event} memory from {sibling_name}: {note}")


def get_seasonal_memory(sibling_name: str, event: str):
    """
    Return a few plausible memories for the given event.
    Can return notes from any sibling — shared memory pool.
    """
    memory_data = _load_json(SEASONAL_FILE, {})
    memories = memory_data.get(event.lower(), [])
    if not memories:
        return []

    # Mix some variance so it doesn’t always recall the same ones
    slice_count = random.randint(1, min(3, len(memories)))
    picks = random.sample(memories, slice_count)
    formatted = [
        f"{m['sibling']} said '{m['note']}' ({m['timestamp'].split('T')[0]})"
        for m in picks
    ]
    return formatted


# ---------------------------------------------------------------------------
# Personal notes interface (optional)
# ---------------------------------------------------------------------------

def add_personal_note(sibling_name: str, text: str):
    """
    Each sibling can append a short reflective or diary-like note.
    This is stored in their individual memory file under memory["recent_notes"].
    """
    path = os.path.join(MEMORY_BASE, f"{sibling_name}_Memory.json")
    data = _load_json(path, {"projects": {}, "recent_notes": [], "seasonal_memory": {}})
    data.setdefault("recent_notes", [])
    note = {
        "text": text,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    data["recent_notes"].append(note)
    data["recent_notes"] = data["recent_notes"][-30:]  # trim
    _save_json(path, data)
    log_event(f"[NOTE] {sibling_name} added personal note: {text}")


def get_recent_personal_notes(sibling_name: str, count: int = 3):
    """Retrieve the last few personal notes from a sibling’s memory file."""
    path = os.path.join(MEMORY_BASE, f"{sibling_name}_Memory.json")
    data = _load_json(path, {"recent_notes": []})
    return [n["text"] for n in data.get("recent_notes", [])[-count:]]


# ---------------------------------------------------------------------------
# Debug & utility
# ---------------------------------------------------------------------------

def summarize_shared_memory():
    """Return a summary dictionary of all shared seasonal memories."""
    data = _load_json(SEASONAL_FILE, {})
    summary = {event: len(memories) for event, memories in data.items()}
    log_event(f"[MEMORY SUMMARY] {summary}")
    return summary
