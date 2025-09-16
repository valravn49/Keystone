import os
from datetime import datetime

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def _file_path(name: str) -> str:
    return os.path.join(DATA_DIR, name)

def _log_line(filename: str, entry: str):
    with open(_file_path(filename), "a", encoding="utf-8") as f:
        f.write(entry + "\n")

def _read_lines(filename: str, limit: int = 10):
    path = _file_path(filename)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return lines[-limit:] if limit else lines

def _timestamp() -> str:
    return datetime.now().isoformat()

def _tag_if_spontaneous(status: str, spontaneous: bool) -> str:
    return f"[SPONTANEOUS] {status}" if spontaneous and not status.startswith("[SPONTANEOUS]") else status

# ---- Logging functions ----
def log_chastity(user, status, notes="", spontaneous=False):
    status = _tag_if_spontaneous(status, spontaneous)
    _log_line("chastity_times.txt", f"{_timestamp()} | {user} | {status} | {notes}")

def read_chastity(limit=10): return _read_lines("chastity_times.txt", limit)

def log_plug(user, status, notes="", spontaneous=False):
    status = _tag_if_spontaneous(status, spontaneous)
    _log_line("plug_times.txt", f"{_timestamp()} | {user} | {status} | {notes}")

def read_plug(limit=10): return _read_lines("plug_times.txt", limit)

def log_anal(user, action, notes="", spontaneous=False):
    action = _tag_if_spontaneous(action, spontaneous)
    _log_line("anal_times.txt", f"{_timestamp()} | {user} | {action} | {notes}")

def read_anal(limit=10): return _read_lines("anal_times.txt", limit)

def log_oral(user, task, notes="", spontaneous=False):
    task = _tag_if_spontaneous(task, spontaneous)
    _log_line("oral_tasks.txt", f"{_timestamp()} | {user} | {task} | {notes}")

def read_oral(limit=10): return _read_lines("oral_tasks.txt", limit)

def log_training(user, task, notes="", spontaneous=False):
    task = _tag_if_spontaneous(task, spontaneous)
    _log_line("training_tasks.txt", f"{_timestamp()} | {user} | {task} | {notes}")

def read_training(limit=10): return _read_lines("training_tasks.txt", limit)

def log_denial(user, event, notes="", spontaneous=False):
    event = _tag_if_spontaneous(event, spontaneous)
    _log_line("denial_tracker.txt", f"{_timestamp()} | {user} | {event} | {notes}")

def read_denial(limit=10): return _read_lines("denial_tracker.txt", limit)

# ---- Parser ----
def _has_any(msg, words): return any(w in msg for w in words)
def _detect_category(msg):
    if _has_any(msg, ["plug","buttplug"]): return "plug"
    if _has_any(msg, ["chastity","cage"]): return "chastity"
    if _has_any(msg, ["anal","dilate"]): return "anal"
    if _has_any(msg, ["oral","mouth"]): return "oral"
    if _has_any(msg, ["training","exercise"]): return "training"
    if _has_any(msg, ["denial","edge","ruin"]): return "denial"
    return None

def parse_data_command(user, message):
    msg = message.lower()
    spontaneous = "[spontaneous]" in msg

    if _has_any(msg, ["show","get","list","history"]):
        cat = _detect_category(msg)
        if cat == "plug": return True, "\n".join(read_plug()), None
        if cat == "chastity": return True, "\n".join(read_chastity()), None
        if cat == "anal": return True, "\n".join(read_anal()), None
        if cat == "oral": return True, "\n".join(read_oral()), None
        if cat == "training": return True, "\n".join(read_training()), None
        if cat == "denial": return True, "\n".join(read_denial()), None
        return False, "", None

    if _has_any(msg, ["log","record","note"]) or spontaneous:
        cat = _detect_category(msg)
        if cat == "plug":
            log_plug(user, "session", message, spontaneous)
            return True, "🍑 Plug log updated.", read_plug(1)[-1]
        if cat == "chastity":
            log_chastity(user, "status", message, spontaneous)
            return True, "🔒 Chastity log updated.", read_chastity(1)[-1]
        if cat == "anal":
            log_anal(user, "session", message, spontaneous)
            return True, "🍑 Anal log updated.", read_anal(1)[-1]
        if cat == "oral":
            log_oral(user, "task", message, spontaneous)
            return True, "👄 Oral log updated.", read_oral(1)[-1]
        if cat == "training":
            log_training(user, "task", message, spontaneous)
            return True, "📘 Training log updated.", read_training(1)[-1]
        if cat == "denial":
            log_denial(user, "event", message, spontaneous)
            return True, "⏳ Denial log updated.", read_denial(1)[-1]
        return False, "", None

    return False, "", None

# ---- Cross-file summary ----
def cross_file_summary(user):
    return (
        f"📊 Cross-file summary for {user}\n\n"
        f"Chastity:\n" + "\n".join(read_chastity(3)) + "\n\n"
        f"Plug:\n" + "\n".join(read_plug(3)) + "\n\n"
        f"Anal:\n" + "\n".join(read_anal(3)) + "\n\n"
        f"Oral:\n" + "\n".join(read_oral(3)) + "\n\n"
        f"Training:\n" + "\n".join(read_training(3)) + "\n\n"
        f"Denial:\n" + "\n".join(read_denial(3))
    )
