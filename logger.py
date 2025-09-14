import os
from datetime import datetime

LOG_DIR = "data"
LOG_FILE = os.path.join(LOG_DIR, "memory_log.txt")
ARCHIVE_DIR = os.path.join(LOG_DIR, "log_archive")
MAX_LOG_SIZE = 1 * 1024 * 1024  # 1 MB

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

def rotate_log_if_needed():
    """Rotate log if file exceeds MAX_LOG_SIZE."""
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_name = f"memory_log_{timestamp}.txt"
        archive_path = os.path.join(ARCHIVE_DIR, archive_name)
        os.rename(LOG_FILE, archive_path)
        print(f"[LOGGER] Rotated log → {archive_path}")

def append_log(entry: str):
    """Append a raw line to the log file."""
    rotate_log_if_needed()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()} {entry}\n")

# ✅ This is the missing function
def log_event(entry: str):
    """Alias for append_log, keeps compatibility with main.py."""
    append_log(entry)

def append_conversation_log(sister: str, role: str, theme: str, user_message: str, content: str):
    entry = (
        f"[CONVERSATION] {sister} ({role}, theme={theme}) "
        f"responded to: \"{user_message}\" → \"{content}\""
    )
    append_log(entry)

def append_ritual_log(sister: str, role: str, theme: str, content: str):
    entry = (
        f"[RITUAL] {sister} ({role}, theme={theme}) "
        f"sent ritual message → \"{content}\""
    )
    append_log(entry)

# --- Structured domain-specific logs ---
def log_cage_event(user: str, status: str, notes: str = ""):
    append_log(f"[CAGE] {user} status={status} notes={notes}")

def log_plug_event(user: str, size: str, duration: str, notes: str = ""):
    append_log(f"[PLUG] {user} size={size}, duration={duration}, notes={notes}")

def log_service_event(user: str, task: str, result: str, notes: str = ""):
    append_log(f"[SERVICE] {user} task={task}, result={result}, notes={notes}")
