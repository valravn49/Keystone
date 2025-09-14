import os
from datetime import datetime

LOG_FILE = os.path.join("data", "memory_log.txt")

def append_log(entry_type: str, sister: str, role: str, theme: str, content: str, user_message: str = None):
    """Append a structured log entry to memory_log.txt"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"--- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        f.write(f"Type: {entry_type}\n")
        f.write(f"Sister: {sister} ({role})\n")
        f.write(f"Theme: {theme}\n")
        if user_message:
            f.write(f"User said: {user_message}\n")
        f.write(f"Message: {content}\n\n")

def append_ritual_log(sister: str, role: str, theme: str, content: str):
    append_log("Ritual", sister, role, theme, content)

def append_conversation_log(sister: str, role: str, theme: str, user_message: str, content: str):
    append_log("Conversation", sister, role, theme, content, user_message=user_message)
