# workouts.py
import os
import json
from datetime import datetime, date

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, "workouts_config.json")
DATA_FILE = os.path.join(DATA_DIR, "workouts_data.json")

# Default kcal/min rates
WORKOUTS = {
    "running": 10,
    "cycling": 8,
    "yoga": 4,
    "pushups": 7,
    "squats": 6,
    "plank": 5,
    "stretching": 3,
    "cardio": 8,
    "posture": 2,
}

# 4-day rotation cycle
WORKOUT_ROTATION = {
    0: {
        "title": "Upper Body Strength",
        "items": [
            "Push-ups – 3 sets of 12",
            "Plank – 3 × 45 sec",
            "Chair Dips – 3 × 10",
        ],
    },
    1: {
        "title": "Lower Body Strength",
        "items": [
            "Squats – 3 sets of 15",
            "Lunges – 3 × 12 each leg",
            "Glute Bridges – 3 × 15",
        ],
    },
    2: {
        "title": "Core & Mixed Cardio",
        "items": [
            "Mountain Climbers – 3 × 30 sec",
            "Sit-ups – 3 × 15",
            "Burpees – 3 × 10",
        ],
    },
    3: {
        "title": "Posture, Cardio & Stretching",
        "items": [
            "Light Jog – 10 min",
            "Posture Alignment Drills – 5 min",
            "Full-body Stretch Routine – 10 min",
        ],
    },
}

# Data storage
data = {"workout_log": []}


# ---------------- Persistence ----------------
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


# ---------------- Validation & Calories ----------------
def validate_workout(name: str) -> bool:
    return name.lower() in WORKOUTS


def calculate_calories_burned(name: str, duration: int) -> int:
    """duration in minutes"""
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


# ---------------- Logging & Summaries ----------------
def log_workout(user: str, name: str, duration: int):
    if not validate_workout(name):
        raise ValueError(f"Unknown workout: {name}")
    calories = calculate_calories_burned(name, duration)
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

    total_minutes = sum(w["duration"] for w in workouts_today)
    total_calories = sum(w["calories"] for w in workouts_today)

    summary = (
        f"📊 Workout Summary for {today}:\n"
        f"- Sessions: {len(workouts_today)}\n"
        f"- Total Minutes: {total_minutes}\n"
        f"- Total Calories Burned: {total_calories}\n"
    )
    return summary


# ---------------- Rotation ----------------
def get_today_workout(target_date: date = None) -> str:
    """Return workout block based on 4-day rotation."""
    if target_date is None:
        target_date = datetime.now().date()

    day_index = (target_date.toordinal() % 4)
    block = WORKOUT_ROTATION[day_index]

    lines = [f"**{block['title']}**"]
    lines.extend([f"- {item}" for item in block["items"]])
    return "\n".join(lines)


# ---------------- Init ----------------
_load_data()
