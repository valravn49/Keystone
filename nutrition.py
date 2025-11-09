# nutrition.py
import os
import json
from datetime import datetime
from workouts import validate_workout, calculate_calories_burned

DATA_FILE = os.path.join("data", "nutrition_data.json")

data = {
    "food_log": [],
    "workout_log": [],
    "targets": {"weight_loss": 1800, "maintenance": 2200}
}

def _load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {
                "food_log": [],
                "workout_log": [],
                "targets": {"weight_loss": 1800, "maintenance": 2200}
            }

def _save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def log_food_entry(user: str, food: str, calories: int):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "food": food,
        "calories": calories
    }
    data["food_log"].append(entry)
    _save_data()
    return entry

def log_workout_completion(user: str, workout_name: str, duration: int):
    if not validate_workout(workout_name):
        raise ValueError(f"Unknown workout: {workout_name}")
    calories_burned = calculate_calories_burned(workout_name, duration)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "workout": workout_name,
        "duration": duration,
        "calories": calories_burned
    }
    data["workout_log"].append(entry)
    _save_data()
    return calories_burned

def set_calorie_targets(weight_loss: int, maintenance: int):
    data["targets"] = {"weight_loss": weight_loss, "maintenance": maintenance}
    _save_data()

def summarize_daily_nutrition():
    today = datetime.now().date()
    food_today = [f for f in data["food_log"] if datetime.fromisoformat(f["timestamp"]).date() == today]
    workout_today = [w for w in data["workout_log"] if datetime.fromisoformat(w["timestamp"]).date() == today]

    total_food = sum(f["calories"] for f in food_today)
    total_burned = sum(w["calories"] for w in workout_today)
    net = total_food - total_burned

    summary = (
        f"📊 Daily Summary for {today}:\n"
        f"- Calories Consumed: {total_food}\n"
        f"- Calories Burned: {total_burned}\n"
        f"- Net Calories: {net}\n"
        f"- Targets → Loss: {data['targets']['weight_loss']}, Maintenance: {data['targets']['maintenance']}"
    )
    return summary

# Ensure data file is loaded at startup
_load_data()
