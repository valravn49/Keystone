import os
import json
from datetime import datetime

# ==============================
# File Paths
# ==============================
NUTRITION_FILE = "data/nutrition_log.jsonl"
TARGET_FILE = "data/nutrition_targets.json"

os.makedirs("data", exist_ok=True)

# ==============================
# Core Logging Functions
# ==============================
def log_meal(user: str, description: str, calories: int, macros: dict):
    """Append a meal entry to the log file."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "description": description,
        "calories": calories,
        "macros": macros,
    }
    with open(NUTRITION_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def read_meals():
    """Return all logged meals as a list of dicts."""
    if not os.path.exists(NUTRITION_FILE):
        return []
    with open(NUTRITION_FILE, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def delete_last_meal(user: str):
    """Delete the last logged meal for a given user."""
    meals = read_meals()
    filtered = []
    removed = False
    for m in reversed(meals):
        if not removed and m["user"] == user:
            removed = True
            continue
        filtered.insert(0, m)
    with open(NUTRITION_FILE, "w", encoding="utf-8") as f:
        for m in filtered:
            f.write(json.dumps(m) + "\n")
    return removed

def edit_last_meal(user: str, description: str = None, calories: int = None, macros: dict = None):
    """Edit the most recent meal for a user."""
    meals = read_meals()
    for m in reversed(meals):
        if m["user"] == user:
            if description: m["description"] = description
            if calories: m["calories"] = calories
            if macros: m["macros"] = macros
            break
    with open(NUTRITION_FILE, "w", encoding="utf-8") as f:
        for m in meals:
            f.write(json.dumps(m) + "\n")
    return True

# ==============================
# Target Handling
# ==============================
def set_targets(user: str, maintenance: int, weightloss: int):
    targets = {}
    if os.path.exists(TARGET_FILE):
        with open(TARGET_FILE, "r", encoding="utf-8") as f:
            targets = json.load(f)
    targets[user] = {"maintenance": maintenance, "weightloss": weightloss}
    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        json.dump(targets, f, indent=2)
    return targets[user]

def get_targets(user: str):
    if not os.path.exists(TARGET_FILE):
        return None
    with open(TARGET_FILE, "r", encoding="utf-8") as f:
        targets = json.load(f)
    return targets.get(user, None)

# ==============================
# Summaries
# ==============================
def daily_summary(user: str):
    """Return today's calorie intake and compare to targets."""
    today = datetime.utcnow().date().isoformat()
    meals = [m for m in read_meals() if m["user"] == user and m["timestamp"].startswith(today)]
    total = sum(m["calories"] for m in meals)

    targets = get_targets(user)
    if not targets:
        return f"Total today: {total} kcal. (No targets set)."

    return (
        f"Total today: {total} kcal | "
        f"Maintenance target: {targets['maintenance']} kcal | "
        f"Weightloss target: {targets['weightloss']} kcal"
    )
