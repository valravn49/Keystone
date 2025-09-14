import os
from datetime import datetime

# Location of memory log
LOG_FILE = "data/memory_log.txt"

def append_memory_log(lead, rest, supports, theme, period, details):
    """
    Append a structured memory entry to memory_log.txt

    Args:
        lead (str): Lead sister's name
        rest (str): Resting sister's name
        supports (list[str]): List of supporting sisters
        theme (str): Current weekly theme
        period (str): "Morning" or "Night"
        details (list[str]): Free-text details to append
    """
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H:%M:%S")

    header = f"=== {today} ({period} @ {timestamp}) ===\n"
    rotation = (
        f"Lead: {lead} | Rest: {rest} | "
        f"Supports: {', '.join(supports) if supports else 'None'}\n"
        f"Theme: {theme}\n"
    )
    body = "\n".join(f"- {d}" for d in details) + "\n"

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(header)
        f.write(rotation + "\n")
        f.write(body + "\n")

    print(f"[MEMORY LOG] Appended {period} entry for {today}")
