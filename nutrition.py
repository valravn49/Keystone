# nutrition.py
from datetime import datetime
from workouts import validate_workout, calculate_calories_burned

# ==============================
# In-Memory Storage
# ==============================
nutrition_log = []   # list of dicts {user, food, calories, time}
workout_log = []     # list of dicts {user, workout, duration, calories, time}
calorie_targets = {"loss": None, "maintenance": None}

# ==============================
# Food Logging
# ==============================
def log_food_entry(user: str, food: str, calories: int):
    """Log a food entry with calories."""
    entry = {
        "user": user,
        "food": food,
        "calories": calories,
        "time": datetime.now()
    }
    nutrition_log.append(entry)
    return entry

# ==============================
# Workout Logging
# ==============================
def log_workout_completion(user: str, workout_name: str, duration: int) -> int:
    """Log a workout session and return calories burned."""
    if not validate_workout(workout_name):
        raise ValueError(f"Unknown workout: {workout_name}")
    calories = calculate_calories_burned(workout_name, duration)
    entry = {
        "user": user,
        "workout": workout_name,
        "duration": duration,
        "calories": calories,
        "time": datetime.now()
    }
    workout_log.append(entry)
    return calories

# ==============================
# Calorie Targets
# ==============================
def set_calorie_targets(weight_loss: int, maintenance: int):
    """Set calorie targets for weight loss and maintenance."""
    calorie_targets["loss"] = weight_loss
    calorie_targets["maintenance"] = maintenance
    return calorie_targets

# ==============================
# Daily Summary
# ==============================
def get_daily_summary() -> str:
    """Return a breakdown of today’s calories in, out, net, and targets."""
    today = datetime.now().date()
    total_food = sum(e["calories"] for e in nutrition_log if e["time"].date() == today)
    total_burn = sum(e["calories"] for e in workout_log if e["time"].date() == today)
    net = total_food - total_burn

    return (
        f"📊 **Today’s Summary**\n"
        f"- Calories In (food): {total_food} kcal\n"
        f"- Calories Out (workouts): {total_burn} kcal\n"
        f"- Net: {net} kcal\n"
        f"- Targets → Loss: {calorie_targets['loss']} kcal | "
        f"Maintenance: {calorie_targets['maintenance']} kcal"
    )
