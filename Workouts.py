import os
import json
from datetime import datetime

WORKOUT_FILE = "data/workout_log.jsonl"
os.makedirs("data", exist_ok=True)

# ==============================
# Workout Library
# ==============================
WORKOUT_LIBRARY = {
    "pushups": {"sets": 3, "reps": "10–15", "rest": "60s",
                "instructions": "Keep body straight, lower chest to floor, push back up."},
    "squats": {"sets": 3, "reps": "12–20", "rest": "60s",
               "instructions": "Feet shoulder-width, lower hips, thighs parallel, drive up."},
    "plank": {"sets": 3, "reps": "30–60s hold", "rest": "60s",
              "instructions": "Keep core tight, elbows under shoulders, avoid sagging hips."},
    "burpees": {"sets": 3, "reps": "8–12", "rest": "90s",
                "instructions": "Drop into pushup, jump feet in, explode upward jump."},
    "lunges": {"sets": 3, "reps": "10/leg", "rest": "60s",
               "instructions": "Step forward, knees 90°, push back through heel."},
    "forward_fold": {"sets": 2, "reps": "30–60s hold", "rest": "30s",
                     "instructions": "Fold forward at hips, relax back, stretch hamstrings."},
    "dips": {"sets": 3, "reps": "8–12", "rest": "90s",
             "instructions": "Use chair/bench, lower body until elbows 90°, push back up."},
    "glute_bridge": {"sets": 3, "reps": "12–20", "rest": "60s",
                     "instructions": "Lie on back, push hips upward, squeeze glutes."},
    "leg_raises": {"sets": 3, "reps": "10–15", "rest": "60s",
                   "instructions": "Lie on back, lift straight legs to 90°, control down."},
    "mountain_climbers": {"sets": 3, "reps": "20–40s", "rest": "60s",
                          "instructions": "Plank position, alternate knees to chest quickly."},
    "jump_squats": {"sets": 3, "reps": "8–15", "rest": "90s",
                    "instructions": "Perform squat, explode upward jump, land softly."},
    "cat_cow": {"sets": 2, "reps": "5–10 cycles", "rest": "30s",
                "instructions": "On hands/knees, alternate arching & rounding spine."},
    "diamond_pushups": {"sets": 3, "reps": "6–12", "rest": "90s",
                        "instructions": "Hands form diamond, lower chest, elbows close to body."},
    "sumo_squats": {"sets": 3, "reps": "12–20", "rest": "60s",
                    "instructions": "Feet wide, toes out, squat deeply, engage inner thighs."},
    "side_plank": {"sets": 3, "reps": "20–45s/side", "rest": "60s",
                   "instructions": "Lie on side, lift hips, hold straight line."},
    "high_knees": {"sets": 3, "reps": "20–40s", "rest": "60s",
                   "instructions": "Run in place, drive knees toward chest quickly."},
    "reverse_lunges": {"sets": 3, "reps": "10/leg", "rest": "60s",
                       "instructions": "Step back, lower until knees 90°, return to start."},
    "shoulder_openers": {"sets": 2, "reps": "5–10 cycles", "rest": "30s",
                         "instructions": "Clasp hands behind back, open chest, stretch shoulders."},
    "deep_breathing": {"sets": 2, "reps": "5 mins", "rest": "—",
                       "instructions": "Slow inhale through nose, exhale fully through mouth."}
}

# ==============================
# 4-Day Rotation
# ==============================
ROTATION = {
    "day1": {"morning": ["pushups", "squats", "plank"],
             "night": ["burpees", "lunges", "forward_fold"]},
    "day2": {"morning": ["dips", "glute_bridge", "leg_raises"],
             "night": ["mountain_climbers", "jump_squats", "cat_cow"]},
    "day3": {"morning": ["diamond_pushups", "sumo_squats", "side_plank"],
             "night": ["high_knees", "reverse_lunges", "shoulder_openers"]},
    "day4": {"morning": ["cat_cow", "forward_fold", "shoulder_openers"],
             "night": ["plank", "glute_bridge", "deep_breathing"]},  # Active rest day
}

def get_workout_routine(day_index: int, time_of_day="morning"):
    """Return structured workout routine for a given day/time."""
    keys = list(ROTATION.keys())
    day_key = keys[day_index % len(keys)]
    return ROTATION[day_key][time_of_day]

def workout_summary(routine):
    """Format workout instructions."""
    lines = []
    for ex in routine:
        w = WORKOUT_LIBRARY[ex]
        lines.append(
            f"**{ex.replace('_',' ').capitalize()}** – {w['sets']} sets of {w['reps']}, rest {w['rest']}.\n"
            f"➡️ {w['instructions']}"
        )
    return "\n\n".join(lines)

def log_workout(user: str, time_of_day: str, completed: list):
    """Log a workout entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "time_of_day": time_of_day,
        "completed": completed,
    }
    with open(WORKOUT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def read_workouts():
    if not os.path.exists(WORKOUT_FILE):
        return []
    with open(WORKOUT_FILE, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]
