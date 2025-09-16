# data_manager.py
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


# ------------------------------
# Specific Logs
# ------------------------------
def log_chastity(user: str, status: str, notes: str = ""):
    entry = f"{datetime.now().isoformat()} | {user} | {status} | {notes}"
    _log_line("chastity_times.txt", entry)

def read_chastity(limit: int = 10):
    return _read_lines("chastity_times.txt", limit)


def log_plug(user: str, status: str, notes: str = ""):
    entry = f"{datetime.now().isoformat()} | {user} | {status} | {notes}"
    _log_line("plug_times.txt", entry)

def read_plug(limit: int = 10):
    return _read_lines("plug_times.txt", limit)


def log_anal(user: str, action: str, notes: str = ""):
    entry = f"{datetime.now().isoformat()} | {user} | {action} | {notes}"
    _log_line("anal_times.txt", entry)

def read_anal(limit: int = 10):
    return _read_lines("anal_times.txt", limit)


def log_oral(user: str, task: str, notes: str = ""):
    entry = f"{datetime.now().isoformat()} | {user} | {task} | {notes}"
    _log_line("oral_tasks.txt", entry)

def read_oral(limit: int = 10):
    return _read_lines("oral_tasks.txt", limit)


def log_training(user: str, task: str, notes: str = ""):
    entry = f"{datetime.now().isoformat()} | {user} | {task} | {notes}"
    _log_line("training_tasks.txt", entry)

def read_training(limit: int = 10):
    return _read_lines("training_tasks.txt", limit)


def log_denial(user: str, event: str, notes: str = ""):
    entry = f"{datetime.now().isoformat()} | {user} | {event} | {notes}"
    _log_line("denial_tracker.txt", entry)

def read_denial(limit: int = 10):
    return _read_lines("denial_tracker.txt", limit)


# ------------------------------
# Natural Language Parser
# ------------------------------
def _contains(msg: str, *keywords):
    return all(k in msg for k in keywords)

def parse_data_command(user: str, message: str):
    """
    Parse flexible natural language commands like:
      "aria log plug time start now"
      "ivy record chastity locked"
      "log anal training"
      "show plug"
    Returns (handled: bool, response: str, recall: str|None)
    """
    msg = message.lower()

    # --- Logging ---
    if "log" in msg or "record" in msg:
        if "plug" in msg:
            status = "start" if "start" in msg else "stop"
            log_plug(user, status, message)
            return True, "🍑 Plug log updated.", read_plug(1)[-1]

        if "chastity" in msg:
            status = "unlocked" if "unlock" in msg else "locked"
            log_chastity(user, status, message)
            return True, f"🔒 Chastity log updated: {status}", read_chastity(1)[-1]

        if "anal" in msg:
            log_anal(user, "session", message)
            return True, "🍑 Anal log updated.", read_anal(1)[-1]

        if "oral" in msg:
            log_oral(user, "task", message)
            return True, "👄 Oral log updated.", read_oral(1)[-1]

        if "training" in msg:
            log_training(user, "task", message)
            return True, "📘 Training log updated.", read_training(1)[-1]

        if "denial" in msg:
            log_denial(user, "event", message)
            return True, "⏳ Denial log updated.", read_denial(1)[-1]

    # --- Reading ---
    if any(k in msg for k in ["show", "get", "read", "list"]):
        if "plug" in msg:
            return True, "\n".join(read_plug()), None
        if "chastity" in msg:
            return True, "\n".join(read_chastity()), None
        if "anal" in msg:
            return True, "\n".join(read_anal()), None
        if "oral" in msg:
            return True, "\n".join(read_oral()), None
        if "training" in msg:
            return True, "\n".join(read_training()), None
        if "denial" in msg:
            return True, "\n".join(read_denial()), None

    return False, "", None
