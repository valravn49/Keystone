# workouts.py
import os
import json
from datetime import datetime, timedelta

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, "workouts_config.json")
DATA_FILE = os.path.join(DATA_DIR, "workouts_data.json")

# 4-Day Rotation Plan
ROTATION = {
    1: {
        "title": "🌸 Waist Slimming & Core Control",
        "exercises": [
            ("Standing Twists", "1 min", "2 sets"),
            ("Russian Twists (no weight)", "30 sec", "2 sets"),
            ("Leg Raises", "10–12 reps", "2–3 sets"),
            ("Plank (elbows)", "30–60 sec", "2 sets"),
            ("Side Plank (each side)", "20–30 sec", "2 sets"),
        ],
    },
    2: {
        "title": "🍑 Leg & Booty Shaping",
        "exercises": [
            ("Glute Bridges", "15 reps", "3 sets"),
            ("Donkey Kicks (each leg)", "15 reps", "2 sets"),
            ("Fire Hydrants (each leg)", "15 reps", "2 sets"),
            ("Bodyweight Squats", "15–20 reps", "3 sets"),
            ("Wall Sit", "30–60 sec", "2 sets"),
        ],
    },
    3: {
        "title": "💪 Upper Body Toning (Lean, Not Buff)",
        "exercises": [
            ("Knee Pushups / Incline Pushups", "10–15 reps", "2–3 sets"),
            ("Wall Angels (posture work)", "10 reps", "2 sets"),
            ("Arm Circles (small & slow)", "1 min", "2 sets"),
            ("Shoulder Taps (from plank)", "30 sec", "2 sets"),
        ],
    },
    4: {
        "title": "✨ Posture, Cardio & Feminine Stretching",
        "exercises": [
            ("Warm-up: Arm Circles", "30 sec each direction", "—"),
            ("Warm-up: Leg Swings", "30 sec each leg", "—"),
            ("Warm-up: Hip Circles", "30 sec each direction", "—"),
            ("Jumping Jacks", "1 min", "—"),
            ("Dynamic Toe Touches", "1 min", "—"),
            ("Cat-Cow (back & hips)", "5–10 reps", "—"),
            ("Standing Forward Fold", "20–30 sec", "—"),
            ("Cobra Stretch (abs)", "20–30 sec", "—"),
            ("Pigeon Pose (hips & glutes)", "20–30 sec", "—"),
            ("Shoulder Stretches", "20–30 sec", "—"),
            ("Neck Rolls & Breathing", "5 deep breaths", "—"),
        ],
    },
}

data = {"workout_log": []}


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


def get_today_index(date: datetime = None) -> int:
    """Return which day in the 4-day cycle today is (1–4)."""
    if date is None:
        date = datetime.now().date()
    day_number = (date.toordinal() % 4) + 1
    return day_number


def get_today_workout(date: datetime = None) -> str:
    """Return the formatted workout plan for today (or given date)."""
    idx = get_today_index(date)
    block = ROTATION[idx]

    header = f"{block['title']}\n"
    lines = [f"• {ex[0]} — {ex[1]} ({ex[2]})" for ex in block["exercises"]]
    return header + "\n".join(lines)


def log_workout(user: str, date: datetime = None):
    """Log that the user completed today’s workout."""
    idx = get_today_index(date)
    block = ROTATION[idx]
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "workout_day": idx,
        "title": block["title"],
    }
    data["workout_log"].append(entry)
    _save_data()
    return entry


def get_workout_summary():
    today = datetime.now().date()
    logs = [
        w for w in data["workout_log"]
        if datetime.fromisoformat(w["timestamp"]).date() == today
    ]
    if not logs:
        return "📊 No workouts logged today."

    summary = f"📊 Workout Summary for {today}:\n"
    for w in logs:
        summary += f"- {w['user']} completed: {w['title']}\n"
    return summary


# Load at startup
_load_data()
