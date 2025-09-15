import os
import json
import datetime

DATA_DIR = "data"
NUTRITION_LOG = os.path.join(DATA_DIR, "nutrition_log.jsonl")

os.makedirs(DATA_DIR, exist_ok=True)


def log_meal(user: str, description: str, calories: int, macros: dict):
    """
    Append a meal entry to the nutrition log.
    macros = {"protein": g, "fat": g, "carbs": g}
    """
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "user": user,
        "description": description,
        "calories": calories,
        "macros": macros,
    }
    with open(NUTRITION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def summarize_daily_calories(user: str, date: str = None):
    """
    Summarize total calories and macros for a given user on a date.
    Default = today (UTC).
    """
    if not os.path.exists(NUTRITION_LOG):
        return {"calories": 0, "macros": {}, "count": 0}

    if not date:
        date = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    total_calories = 0
    macro_totals = {"protein": 0, "fat": 0, "carbs": 0}
    count = 0

    with open(NUTRITION_LOG, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")
                if ts.startswith(date) and entry.get("user") == user:
                    total_calories += entry.get("calories", 0)
                    for k in macro_totals:
                        macro_totals[k] += entry.get("macros", {}).get(k, 0)
                    count += 1
            except json.JSONDecodeError:
                continue

    return {"calories": total_calories, "macros": macro_totals, "count": count}
