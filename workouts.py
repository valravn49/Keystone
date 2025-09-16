# workouts.py
import os
import json
from datetime import datetime

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, "workouts_config.json")
DATA_FILE = os.path.join(DATA_DIR, "workouts_data.json")

# Default workouts
WORKOUTS = {
    "running": 10,
    "cycling": 8,
    "yoga": 4
}

data = {"workout_log": []}


def _load_data():
    global data, WORKOUTS
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"workout_log": []}

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                WORKOUTS = json.load(f)
        except Exception:
            pass


def _save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(WORKOUTS, f, indent=2)


def validate_workout(name: str) -> bool:
    return name.lower() in WORKOUTS


def calculate_calories_burned(name: str, duration: int) -> int:
    rate = WORKOUTS.get(name.lower())
    if rate is None:
        raise ValueError(f"Unknown workout: {name}")
    return rate * duration


def add_workout(name: str, rate: int):
    WORKOUTS[name.lower()] = rate
    _save_data()


def remove_workout(name: str):
    name = name.lower()
    if name in WORKOUTS:
        del WORKOUTS[name]
    _save_data()


def list_workouts() -> str:
    if not WORKOUTS:
        return "⚠️ No workouts defined."

    header = f"{'Workout':<15} | {'kcal/min':>8}"
    sep = "-" * len(header)
    rows = [f"{w:<15} | {c:>8}" for w, c in WORKOUTS.items()]
    return "\n".join([header, sep] + rows)


def log_workout(user: str, name: str, duration: int):
    if not validate_workout(name):
        raise ValueError(f"Unknown workout: {name}")
    calories = calculate_calories_burned(name, duration)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "workout": name,
        "duration": duration,
        "calories": calories
    }
    data["workout_log"].append(entry)
    _save_data()
    return entry


def get_workout_summary():
    today = datetime.now().date()
    workouts_today = [
        w for w in data["workout_log"]
        if datetime.fromisoformat(w["timestamp"]).date() == today
    ]
    if not workouts_today:
        return "📊 No workouts logged today."

    total_minutes = sum(w["duration"] for w in workouts_today)
    total_calories = sum(w["calories"] for w in workouts_today)

    summary = (
        f"📊 Workout Summary for {today}:\n"
        f"- Sessions: {len(workouts_today)}\n"
        f"- Total Minutes: {total_minutes}\n"
        f"- Total Calories Burned: {total_calories}\n"
    )
    return summary


# Load at startup
_load_data()
