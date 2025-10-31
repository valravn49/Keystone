import os, json
from logger import log_event

BASE_PATH = "/Autonomy/memory"

def _path(name: str) -> str:
    return os.path.join(BASE_PATH, f"{name}_Memory.json")

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[MEMORY][WARN] {path} read error: {e}")
    return default

def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[MEMORY][WARN] {path} save error: {e}")

def get_seasonal_memory(name: str, event: str) -> list[str]:
    path = _path(name)
    mem = _load_json(path, {"seasonal_memory": {}})
    return mem.get("seasonal_memory", {}).get(event, [])

def add_seasonal_memory(name: str, event: str, note: str):
    path = _path(name)
    mem = _load_json(path, {"seasonal_memory": {}})
    sm = mem.setdefault("seasonal_memory", {})
    sm.setdefault(event, []).append(note)
    _save_json(path, mem)
    log_event(f"[MEMORY] {name} → {event}: {note}")
