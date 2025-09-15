import os
import json
from datetime import datetime

DATA_DIR = "data"
NUTRITION_FILE = os.path.join(DATA_DIR, "nutrition.json")

os.makedirs(DATA_DIR, exist_ok=True)

# Ensure nutrition file exists
if not os.path.exists(NUTRITION_FILE):
    with open(NUTRITION_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "calorie_intake": [],
            "workouts": [],
            "targets": {
                "maintenance": 2200,
                "weight_loss": 1800
            }
        }, f, indent=2)

def _load_data():
    with open(NUTRITION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_data(data):
    with open(NUTRITION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ----------------------------
# Food / Calorie Logging
# ----------------------------
def log_food_entry(user: str, food: str, calories: int):
    """Log a food entry with calories."""
    data = _load_data()
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "food": food,
        "calories": calories
    }
    data["calorie_intake"].append(entry)
    _save_data(data)
    return entry

def delete_food_entry(index: int):
    """Delete a food entry by index."""
    data = _load_data()
    if 0 <= index < len(data["calorie_intake"]):
        removed = data["calorie_intake"].pop(index)
        _save_data(data)
        return removed
    return None

def edit_food_entry(index: int, food: str = None, calories: int = None):
    """Edit a logged food entry."""
    data = _load_data()
    if 0 <= index < len(data["calorie_intake"]):
        if food is not None:
            data["calorie_intake"][index]["food"] = food
        if calories is not None:
            data["calorie_intake"][index]["calories"] = calories
        _save_data(data)
        return data["calorie_intake"][index]
    return None

# ----------------------------
# Workout Logging
# ----------------------------
def log_workout_completion(user: str, workout: str, duration: str):
    """Log a completed workout."""
    data = _load_data()
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "workout": workout,
        "duration": duration
    }
    data["workouts"].append(entry)
    _save_data(data)
    return entry

def delete_workout_entry(index: int):
    """Delete a workout log by index."""
    data = _load_data()
    if 0 <= index < len(data["workouts"]):
        removed = data["workouts"].pop(index)
        _save_data(data)
        return removed
    return None

def edit_workout_entry(index: int, workout: str = None, duration: str = None):
    """Edit a logged workout entry."""
    data = _load_data()
    if 0 <= index < len(data["workouts"]):
        if workout is not None:
            data["workouts"][index]["workout"] = workout
        if duration is not None:
            data["workouts"][index]["duration"] = duration
        _save_data(data)
        return data["workouts"][index]
    return None

# ----------------------------
# Calorie Targets
# ----------------------------
def set_calorie_targets(maintenance: int, weight_loss: int):
    """Update calorie targets."""
    data = _load_data()
    data["targets"]["maintenance"] = maintenance
    data["targets"]["weight_loss"] = weight_loss
    _save_data(data)
    return data["targets"]
def get_daily_summary():
    """Return a formatted string of today's nutrition + workouts + totals."""
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, f"{today}.json")

    if not os.path.exists(path):
        return "No entries for today."

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    foods = data.get("foods", [])
    workouts = data.get("workouts", [])
    targets = data.get("targets", {"maintenance": 0, "weight_loss": 0})

    total_calories = sum(f["calories"] for f in foods)

    food_lines = "\n".join([f"- {i}. {f['food']} ({f['calories']} kcal)" for i, f in enumerate(foods)])
    workout_lines = "\n".join([f"- {i}. {w['workout']} ({w['duration']})" for i, w in enumerate(workouts)])

    return (
        f"🍽️ Foods:\n{food_lines or 'None'}\n\n"
        f"💪 Workouts:\n{workout_lines or 'None'}\n\n"
        f"🔥 Total Calories: {total_calories}\n"
        f"🎯 Targets → Maintenance: {targets['maintenance']} kcal, "
        f"Weight Loss: {targets['weight_loss']} kcal"
    )
def get_calorie_targets():
    """Return current calorie targets."""
    data = _load_data()
    return data["targets"]
