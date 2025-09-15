# nutrition.py
import os
from datetime import datetime

DATA_DIR = "data"
CALORIE_LOG = os.path.join(DATA_DIR, "calorie_log.txt")
WORKOUT_LOG = os.path.join(DATA_DIR, "workout_log.txt")

os.makedirs(DATA_DIR, exist_ok=True)

# =========================
# Helpers
# =========================
def _read_log(file_path: str):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()

def _write_log(file_path: str, lines: list):
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

def _format_entry(prefix: str, user: str, detail: str, notes: str = "") -> str:
    return f"{datetime.utcnow().isoformat()} {prefix} {user} {detail} {notes}\n"

# =========================
# Logging functions
# =========================
def log_calories(user: str, calories: int, meal: str, notes: str = ""):
    """Append a calorie intake entry."""
    entry = _format_entry("[CALORIES]", user, f"ate {calories} kcal ({meal})", notes)
    with open(CALORIE_LOG, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"[NUTRITION] Logged calories: {entry.strip()}")

def log_workout_completion(user: str, workout: str, duration: str, notes: str = ""):
    """Append a workout completion entry."""
    entry = _format_entry("[WORKOUT]", user, f"completed {workout} ({duration})", notes)
    with open(WORKOUT_LOG, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"[NUTRITION] Logged workout: {entry.strip()}")

# =========================
# Edit functions
# =========================
def edit_log_entry(file: str, index: int, new_content: str) -> bool:
    """
    Edit a specific entry by line index (0-based).
    Returns True if successful, False otherwise.
    """
    lines = _read_log(file)
    if 0 <= index < len(lines):
        timestamp = datetime.utcnow().isoformat()
        lines[index] = f"{timestamp} {new_content}\n"
        _write_log(file, lines)
        print(f"[NUTRITION] Edited entry {index} in {file}: {new_content}")
        return True
    return False

def delete_log_entry(file: str, index: int) -> bool:
    """
    Delete a specific entry by line index (0-based).
    Returns True if successful, False otherwise.
    """
    lines = _read_log(file)
    if 0 <= index < len(lines):
        removed = lines.pop(index)
        _write_log(file, lines)
        print(f"[NUTRITION] Deleted entry {index} in {file}: {removed.strip()}")
        return True
    return False

# =========================
# Convenience wrappers
# =========================
def edit_calorie_entry(index: int, new_content: str) -> bool:
    return edit_log_entry(CALORIE_LOG, index, f"[CALORIES] {new_content}")

def delete_calorie_entry(index: int) -> bool:
    return delete_log_entry(CALORIE_LOG, index)

def edit_workout_entry(index: int, new_content: str) -> bool:
    return edit_log_entry(WORKOUT_LOG, index, f"[WORKOUT] {new_content}")

def delete_workout_entry(index: int) -> bool:
    return delete_log_entry(WORKOUT_LOG, index)
