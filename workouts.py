# workouts.py
import os
import json
from datetime import datetime, date

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, "workouts_config.json")
DATA_FILE = os.path.join(DATA_DIR, "workouts_data.json")

# Default 4-day workout cycle
WORKOUT_CYCLE = [
    "Day 1: Upper body strength (push/pull split, weights)",
    "Day 2: Lower body focus (squats, deadlifts, legs)",
    "Day 3: Core + conditioning (planks, HIIT, circuits)",
    "Day 4: Stretching, posture, light cardio (rest/active recovery)"
]

data = {"workout_log": []}


# ---------------- Persistence ----------------
def _load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"workout_log": []}


def _save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------- Deterministic Cycle ----------------
def get_today_workout(target_date: date = None):
    """
    Return the workout for the given date, based on a 4-day deterministic cycle.
    Always consistent: the same calendar date yields the same workout.
    """
    if target_date is None:
        target_date = datetime.now().date()

    day_index = target_date.toordinal() % len(WORKOUT_CYCLE)
    return WORKOUT_CYCLE[day_index]


# ---------------- Logging ----------------
def log_workout(user: str, name: str, duration: int, calories: int = None):
    """
    Log a workout session for today.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "workout": name,
        "duration": duration,
        "calories": calories,
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

    total_minutes = sum(w["duration"] for w in workouts_today if w.get("duration"))
    total_calories = sum(w["calories"] or 0 for w in workouts_today)

    summary = (
        f"📊 Workout Summary for {today}:\n"
        f"- Sessions: {len(workouts_today)}\n"
        f"- Total Minutes: {total_minutes}\n"
        f"- Total Calories Burned: {total_calories}\n"
    )
    return summary


# ---------------- Startup ----------------
_load_data()
