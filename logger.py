import os
from datetime import datetime

LOG_DIR = "data"
LOG_FILE = os.path.join(LOG_DIR, "memory_log.txt")
ARCHIVE_DIR = os.path.join(LOG_DIR, "log_archive")
MAX_LOG_SIZE = 1 * 1024 * 1024  # 1 MB per log file

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

def rotate_log_if_needed():
    """Rotate log if file exceeds MAX_LOG_SIZE."""
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_name = f"memory_log_{timestamp}.txt"
        archive_path = os.path.join(ARCHIVE_DIR, archive_name)
        os.rename(LOG_FILE, archive_path)
        print(f"[LOGGER] Rotated log file → {archive_path}")

def append_log(entry: str):
    """Append a raw line to the memory log."""
    rotate_log_if_needed()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()} {entry}\n")

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
