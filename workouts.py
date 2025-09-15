# workouts.py
import json
import os
from datetime import datetime

# ==============================
# File Paths
# ==============================
CONFIG_FILE = "workouts_config.json"   # stores available workouts + kcal/min
DATA_FILE = "workouts_data.json"       # stores completed workout sessions

# ==============================
# In-Memory State
# ==============================
WORKOUTS = {}       # str → kcal/min
workout_log = []    # list of dicts {user, workout, duration, calories, time}


# ==============================
# Persistence Helpers
# ==============================
def _save_config():
    """Persist available workouts to disk."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(WORKOUTS, f, indent=2)


def _load_config():
    """Load available workouts from disk, or initialize defaults."""
    global WORKOUTS
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            WORKOUTS = json.load(f)
    else:
        # default set if no config exists
        WORKOUTS = {
            "running": 10,
            "cycling": 8,
            "swimming": 11,
            "yoga": 4,
            "weightlifting": 6,
            "walking": 5,
            "rowing": 9,
        }
        _save_config()


def _save_data():
    """Persist workout log entries to disk."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(workout_log, f, default=str, indent=2)


def _load_data():
    """Load workout logs from disk if available."""
    global workout_log
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                workout_log = [
                    {**e, "time": datetime.fromisoformat(e["time"])}
                    for e in data
                ]
            except Exception:
                workout_log = []


# ==============================
# Initialize on Import
# ==============================
_load_config()
_load_data()


# ==============================
# Core Functions
# ==============================
def validate_workout(name: str) -> bool:
    """Check if the workout is in the known list."""
    return name.lower() in WORKOUTS


def calculate_calories_burned(name: str, duration: int) -> int:
    """Return calories burned for a workout given minutes."""
    name = name.lower()
    if name not in WORKOUTS:
        raise ValueError(f"Unknown workout: {name}")
    return WORKOUTS[name] * duration


def log_workout(user: str, workout_name: str, duration: int) -> dict:
    """Log a workout entry and persist it separately from nutrition."""
    calories = calculate_calories_burned(workout_name, duration)
    entry = {
        "user": user,
        "workout": workout_name.lower(),
        "duration": duration,
        "calories": calories,
        "time": datetime.now()
    }
    workout_log.append(entry)
    _save_data()
    return entry


def get_workout_summary() -> str:
    """Return today’s workout summary from this module only."""
    today = datetime.now().date()
    total_sessions = sum(1 for e in workout_log if e["time"].date() == today)
    total_minutes = sum(e["duration"] for e in workout_log if e["time"].date() == today)
    total_burn = sum(e["calories"] for e in workout_log if e["time"].date() == today)

    return (
        f"🏋️ **Workout Summary (Today)**\n"
        f"- Sessions: {total_sessions}\n"
        f"- Total Duration: {total_minutes} mins\n"
        f"- Total Calories Burned: {total_burn} kcal"
    )


# ==============================
# Workout Management
# ==============================
def add_workout(name: str, rate: int):
    """Add or update a workout with its kcal/min rate and persist it."""
    WORKOUTS[name.lower()] = rate
    _save_config()


def remove_workout(name: str):
    """Remove a workout by name."""
    name = name.lower()
    if name in WORKOUTS:
        del WORKOUTS[name]
        _save_config()


def list_workouts() -> str:
    """Return a formatted string of available workouts."""
    if not WORKOUTS:
        return "⚠️ No workouts defined."
    return "\n".join([f"- {w}: {c} kcal/min" for w, c in WORKOUTS.items()])
