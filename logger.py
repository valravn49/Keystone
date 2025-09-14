import os
from datetime import datetime

# Base directories
LOG_DIR = "data"
LOG_FILE = os.path.join(LOG_DIR, "memory_log.txt")
ARCHIVE_DIR = os.path.join(LOG_DIR, "log_archive")
SISTERS_DIR = os.path.join(LOG_DIR, "sisters")

MAX_LOG_SIZE = 1 * 1024 * 1024  # 1 MB for rotating main memory log

# Ensure directories exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(SISTERS_DIR, exist_ok=True)

def _timestamp():
    return datetime.utcnow().isoformat()

def rotate_log_if_needed():
    """Rotate memory_log.txt if it exceeds MAX_LOG_SIZE."""
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_name = f"memory_log_{timestamp}.txt"
        archive_path = os.path.join(ARCHIVE_DIR, archive_name)
        os.rename(LOG_FILE, archive_path)
        print(f"[LOGGER] Rotated memory log → {archive_path}")

def _append_to_file(file_path: str, entry: str):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

def append_log(entry: str, sister: str = None):
    """Append a raw line to the main memory log (and sister log if given)."""
    rotate_log_if_needed()
    line = f"{_timestamp()} {entry}"
    _append_to_file(LOG_FILE, line)

    if sister:
        sister_file = os.path.join(SISTERS_DIR, f"{sister}.txt")
        _append_to_file(sister_file, line)

def append_conversation_log(sister: str, role: str, theme: str, user_message: str, content: str):
    """Log conversational events."""
    entry = (
        f"[CONVERSATION] {sister} ({role}, theme={theme}) "
        f"responded to: \"{user_message}\" → \"{content}\""
    )
    append_log(entry, sister=sister)

def append_ritual_log(sister: str, role: str, theme: str, content: str):
    """Log ritual/scheduled events (morning/night)."""
    entry = (
        f"[RITUAL] {sister} ({role}, theme={theme}) "
        f"sent ritual message → \"{content}\""
    )
    append_log(entry, sister=sister)
