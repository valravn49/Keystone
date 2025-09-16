import os
from datetime import datetime, date

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------------
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

# -------------------------
def log_chastity(user: str, status: str, notes: str = "", spontaneous: bool = False):
    status = _tag_if_spontaneous(status, spontaneous)
    entry = f"{_timestamp()} | {user} | {status} | {notes}"
    _log_line("chastity_times.txt", entry)

def read_chastity(limit: int = 10):
    return _read_lines("chastity_times.txt", limit)

def log_plug(user: str, status: str, notes: str = "", spontaneous: bool = False):
    status = _tag_if_spontaneous(status, spontaneous)
    entry = f"{_timestamp()} | {user} | {status} | {notes}"
    _log_line("plug_times.txt", entry)

def read_plug(limit: int = 10):
    return _read_lines("plug_times.txt", limit)

def log_anal(user: str, action: str, notes: str = "", spontaneous: bool = False):
    action = _tag_if_spontaneous(action, spontaneous)
    entry = f"{_timestamp()} | {user} | {action} | {notes}"
    _log_line("anal_times.txt", entry)

def read_anal(limit: int = 10):
    return _read_lines("anal_times.txt", limit)

def log_oral(user: str, task: str, notes: str = "", spontaneous: bool = False):
    task = _tag_if_spontaneous(task, spontaneous)
    entry = f"{_timestamp()} | {user} | {task} | {notes}"
    _log_line("oral_tasks.txt", entry)

def read_oral(limit: int = 10):
    return _read_lines("oral_tasks.txt", limit)

def log_training(user: str, task: str, notes: str = "", spontaneous: bool = False):
    task = _tag_if_spontaneous(task, spontaneous)
    entry = f"{_timestamp()} | {user} | {task} | {notes}"
    _log_line("training_tasks.txt", entry)

def read_training(limit: int = 10):
    return _read_lines("training_tasks.txt", limit)

def log_denial(user: str, event: str, notes: str = "", spontaneous: bool = False):
    event = _tag_if_spontaneous(event, spontaneous)
    entry = f"{_timestamp()} | {user} | {event} | {notes}"
    _log_line("denial_tracker.txt", entry)

def read_denial(limit: int = 10):
    return _read_lines("denial_tracker.txt", limit)

# -------------------------
# Flexible natural parser (kept for compatibility)
import re
_DURATION_REGEX = re.compile(r"(\d+)\s*(hours|hour|hrs|hr|h|minutes|minute|mins|min|m)\b", re.I)
def _has_any(msg: str, words):
    return any(w in msg for w in words)
def _detect_category(msg: str):
    if _has_any(msg, ["plug", "buttplug", "butt plug", "toy"]):
        return "plug"
    if _has_any(msg, ["chastity", "cage", "locked", "unlock"]):
        return "chastity"
    if _has_any(msg, ["anal", "dilate", "stretch"]) and not _has_any(msg, ["oral"]):
        return "anal"
    if _has_any(msg, ["oral", "mouth", "throat", "blowjob", "blow job"]):
        return "oral"
    if _has_any(msg, ["training", "practice", "exercise", "drill", "task", "assignment"]):
        return "training"
    if _has_any(msg, ["denial", "edge", "ruin", "no orgasm", "no release"]):
        return "denial"
    return None
def _normalize_status_for_plug(msg: str) -> str:
    if _has_any(msg, ["start", "insert", "in", "put in", "slip in"]):
        return "start"
    if _has_any(msg, ["stop", "remove", "out", "take out", "pull out"]):
        return "stop"
    return "session"
def _normalize_status_for_chastity(msg: str) -> str:
    if _has_any(msg, ["unlock", "unlocked", "off", "open"]):
        return "unlocked"
    if _has_any(msg, ["lock", "locked", "on", "closed"]):
        return "locked"
    return "status"

def parse_data_command(user: str, message: str):
    msg = message.lower()
    spontaneous = "[spontaneous]" in message.lower()

    # read/show
    if _has_any(msg, ["show", "get", "read", "list", "history", "logs"]):
        cat = _detect_category(msg)
        if cat == "plug":
            lines = read_plug()
            return True, "\n".join(lines) if lines else "No plug entries.", None
        if cat == "chastity":
            lines = read_chastity()
            return True, "\n".join(lines) if lines else "No chastity entries.", None
        if cat == "anal":
            lines = read_anal()
            return True, "\n".join(lines) if lines else "No anal entries.", None
        if cat == "oral":
            lines = read_oral()
            return True, "\n".join(lines) if lines else "No oral entries.", None
        if cat == "training":
            lines = read_training()
            return True, "\n".join(lines) if lines else "No training entries.", None
        if cat == "denial":
            lines = read_denial()
            return True, "\n".join(lines) if lines else "No denial entries.", None
        return False, "", None

    # logging
    is_logging_intent = _has_any(msg, ["log", "record", "note"]) or spontaneous
    if is_logging_intent:
        cat = _detect_category(msg)
        if cat == "plug":
            status = _normalize_status_for_plug(msg)
            log_plug(user, status, message, spontaneous=spontaneous)
            last = read_plug(1)
            return True, "🍑 Plug log updated.", last[-1] if last else None
        if cat == "chastity":
            status = _normalize_status_for_chastity(msg)
            log_chastity(user, status, message, spontaneous=spontaneous)
            last = read_chastity(1)
            return True, f"🔒 Chastity log updated: {status}", last[-1] if last else None
        if cat == "anal":
            action = "session"
            log_anal(user, action, message, spontaneous=spontaneous)
            last = read_anal(1)
            return True, "🍑 Anal log updated.", last[-1] if last else None
        if cat == "oral":
            log_oral(user, "task", message, spontaneous=spontaneous)
            last = read_oral(1)
            return True, "👄 Oral log updated.", last[-1] if last else None
        if cat == "training":
            log_training(user, "task", message, spontaneous=spontaneous)
            last = read_training(1)
            return True, "📘 Training log updated.", last[-1] if last else None
        if cat == "denial":
            log_denial(user, "event", message, spontaneous=spontaneous)
            last = read_denial(1)
            return True, "⏳ Denial log updated.", last[-1] if last else None
        return False, "", None

    return False, "", None

# -------------------------
# Cross-file summary helper
def _parse_iso_date_from_entry(line: str):
    # Expect lines like "2025-09-16T08:12:34 | user | status | notes"
    try:
        ts = line.split("|", 1)[0].strip()
        return datetime.fromisoformat(ts).date()
    except Exception:
        return None

def cross_file_summary(user: str, days: int = 0):
    """
    Aggregate today's (days=0) entries across tracked files and return a formatted summary.
    If days > 0 will include the last `days` days (including today).
    """
    target_date = datetime.now().date()
    start_date = target_date - timedelta(days=days)

    files = {
        "Chastity": "chastity_times.txt",
        "Plug": "plug_times.txt",
        "Anal": "anal_times.txt",
        "Oral": "oral_tasks.txt",
        "Training": "training_tasks.txt",
        "Denial": "denial_tracker.txt"
    }

    sections = []
    for label, fname in files.items():
        lines = _read_lines(fname, limit=1000)  # get all
        filtered = []
        for L in lines:
            d = _parse_iso_date_from_entry(L)
            if not d:
                continue
            if d >= start_date:
                filtered.append(L)
        if filtered:
            sections.append(f"**{label} ({len(filtered)} entries)**\n" + "\n".join(filtered[-10:]))

    if not sections:
        return f"No entries found for {target_date} (or the last {days} days)."

    header = f"Cross-file summary for {target_date} (last {days} days):"
    return header + "\n\n" + "\n\n".join(sections)
