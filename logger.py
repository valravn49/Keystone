import os
from datetime import datetime

LOG_DIR = "data"
LOG_FILE = os.path.join(LOG_DIR, "memory_log.txt")
ARCHIVE_DIR = os.path.join(LOG_DIR, "log_archive")
MAX_LOG_SIZE = 1 * 1024 * 1024  # 1 MB per log file

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Map keywords → project tracker files
CATEGORY_MAP = {
    "chastity": "chastity_times.txt",
    "plug": "plug_times.txt",
    "anal": "anal_times.txt",
    "oral": "oral_tasks.txt",
    "denial": "denial_tracker.txt",
    "training": "training_tasks.txt",
    "style": "Style_and_Shopping_Index.txt",
    "refinement": "Sisters_Refinements_Log.txt",
    "project": "Project_Index.txt",
}

def rotate_log_if_needed():
    """Rotate memory_log.txt if file exceeds MAX_LOG_SIZE."""
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_name = f"memory_log_{timestamp}.txt"
        archive_path = os.path.join(ARCHIVE_DIR, archive_name)
        os.rename(LOG_FILE, archive_path)
        print(f"[LOGGER] Rotated log file → {archive_path}")

def append_log(entry: str):
    """Append entry to memory log and route to trackers if category matches."""
    rotate_log_if_needed()
    timestamped = f"{datetime.utcnow().isoformat()} {entry}\n"

    # Always append to main memory log
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(timestamped)

    # Route to category files
    lowered = entry.lower()
    for keyword, filename in CATEGORY_MAP.items():
        if keyword in lowered:
            filepath = os.path.join(LOG_DIR, filename)
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(timestamped)
            break  # stop after first match

def append_conversation_log(sister: str, role: str, theme: str, user_message: str, content: str):
    """Log conversational events."""
    entry = (
        f"[CONVERSATION] {sister} ({role}, theme={theme}) "
        f"responded to: \"{user_message}\" → \"{content}\""
    )
    append_log(entry)

def append_ritual_log(sister: str, role: str, theme: str, content: str):
    """Log ritual/scheduled events (morning/night)."""
    entry = (
        f"[RITUAL] {sister} ({role}, theme={theme}) "
        f"sent ritual message → \"{content}\""
    )
    append_log(entry)

def log_event(entry: str):
    """Generic logging for system/other events."""
    append_log(f"[EVENT] {entry}")
