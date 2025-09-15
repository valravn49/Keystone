import random
from logger import log_event

# ==============================
# Define full bodyweight workouts with instructions
# ==============================
WORKOUTS = {
    "day1": {  # Upper/Lower/Core
        "morning": [
            {
                "name": "Push-ups",
                "sets": "3 x 12",
                "instructions": [
                    "Keep hands shoulder-width apart",
                    "Lower chest until just above the floor",
                    "Elbows tucked at ~45 degrees",
                    "Push back up keeping body straight"
                ]
            },
            {
                "name": "Squats",
                "sets": "3 x 15",
                "instructions": [
                    "Feet shoulder-width apart",
                    "Lower hips until thighs parallel",
                    "Keep chest up and knees tracking over toes",
                    "Stand tall and squeeze glutes"
                ]
            },
            {
                "name": "Plank",
                "sets": "3 x 30s",
                "instructions": [
                    "Forearms on ground, elbows under shoulders",
                    "Keep body in straight line",
                    "Engage core and glutes",
                    "Do not let hips sag"
                ]
            },
        ],
        "night": [
            {
                "name": "Lunges",
                "sets": "3 x 10 each leg",
                "instructions": [
                    "Step forward and lower until both knees at 90°",
                    "Front knee above ankle, not past toes",
                    "Push through heel to return",
                    "Alternate legs each rep"
                ]
            },
            {
                "name": "Dips (chair)",
                "sets": "3 x 10",
                "instructions": [
                    "Hands on edge of chair, fingers forward",
                    "Lower until elbows at 90°",
                    "Keep back close to chair",
                    "Push up fully but don’t lock elbows"
                ]
            },
            {
                "name": "Leg Raises",
                "sets": "3 x 12",
                "instructions": [
                    "Lie flat, hands under hips",
                    "Lift legs slowly to 90°",
                    "Lower legs without touching floor",
                    "Keep core tight"
                ]
            },
        ]
    },

    "day2": {  # Strength + Core
        "morning": [
            {
                "name": "Incline Push-ups",
                "sets": "3 x 12",
                "instructions": [
                    "Hands on bench or table",
                    "Lower chest toward edge",
                    "Body stays straight",
                    "Push back to start position"
                ]
            },
            {
                "name": "Bulgarian Split Squats",
                "sets": "3 x 10 each leg",
                "instructions": [
                    "Rear foot elevated on chair",
                    "Lower until front thigh parallel",
                    "Keep torso upright",
                    "Drive through front heel to rise"
                ]
            },
            {
                "name": "Side Plank",
                "sets": "3 x 20s each side",
                "instructions": [
                    "Elbow under shoulder",
                    "Lift hips into straight line",
                    "Hold without dropping",
                    "Switch sides"
                ]
            },
        ],
        "night": [
            {
                "name": "Jump Squats",
                "sets": "3 x 12",
                "instructions": [
                    "Perform normal squat",
                    "Explosively jump upward",
                    "Land softly, knees bent",
                    "Repeat immediately"
                ]
            },
            {
                "name": "Diamond Push-ups",
                "sets": "3 x 8",
                "instructions": [
                    "Hands form diamond under chest",
                    "Keep elbows close",
                    "Lower chest slowly",
                    "Push up with triceps focus"
                ]
            },
            {
                "name": "Bicycle Crunches",
                "sets": "3 x 20 (10 per side)",
                "instructions": [
                    "Lie on back, hands behind head",
                    "Bring opposite elbow to knee",
                    "Alternate sides with pedaling motion",
                    "Keep core tight"
                ]
            },
        ]
    },

    "day3": {  # Shoulders/Glutes/Core
        "morning": [
            {
                "name": "Pike Push-ups",
                "sets": "3 x 10",
                "instructions": [
                    "Start in downward dog position",
                    "Bend elbows lowering head to floor",
                    "Push back up through shoulders",
                    "Keep hips high"
                ]
            },
            {
                "name": "Glute Bridges",
                "sets": "3 x 15",
                "instructions": [
                    "Lie on back, knees bent",
                    "Lift hips until straight line knees-shoulders",
                    "Squeeze glutes at top",
                    "Lower slowly"
                ]
            },
            {
                "name": "Russian Twists",
                "sets": "3 x 16 (8 each side)",
                "instructions": [
                    "Sit with knees bent, heels off ground",
                    "Twist torso side to side",
                    "Touch ground beside hip each twist",
                    "Keep core tight"
                ]
            },
        ],
        "night": [
            {
                "name": "Step-ups (chair/bench)",
                "sets": "3 x 12 each leg",
                "instructions": [
                    "Step up with one leg onto chair",
                    "Drive through heel to stand tall",
                    "Step down under control",
                    "Alternate legs"
                ]
            },
            {
                "name": "Decline Push-ups",
                "sets": "3 x 10",
                "instructions": [
                    "Feet elevated on chair",
                    "Hands on floor shoulder-width",
                    "Lower chest slowly",
                    "Push up keeping core tight"
                ]
            },
            {
                "name": "Flutter Kicks",
                "sets": "3 x 30s",
                "instructions": [
                    "Lie on back, hands under hips",
                    "Lift legs a few inches",
                    "Kick legs up/down in small motions",
                    "Keep core braced"
                ]
            },
        ]
    },

    "day4": {  # Recovery / Stretching
        "morning": [
            {
                "name": "Cat-Cow Stretch",
                "sets": "2 x 6 breaths",
                "instructions": [
                    "Start on all fours",
                    "Arch back (cow) while inhaling",
                    "Round spine (cat) while exhaling",
                    "Move slowly and controlled"
                ]
            },
            {
                "name": "Hamstring Stretch",
                "sets": "2 x 20s each side",
                "instructions": [
                    "Sit with one leg extended",
                    "Reach toward foot without rounding back",
                    "Hold stretch gently",
                    "Switch legs"
                ]
            },
            {
                "name": "Child’s Pose",
                "sets": "2 x 30s",
                "instructions": [
                    "Kneel and sit back onto heels",
                    "Stretch arms forward on floor",
                    "Relax shoulders and breathe",
                    "Sink deeper with each exhale"
                ]
            },
        ],
        "night": [
            {
                "name": "Hip Flexor Stretch",
                "sets": "2 x 20s each side",
                "instructions": [
                    "Kneel with one foot forward",
                    "Shift hips forward gently",
                    "Keep chest upright",
                    "Switch legs"
                ]
            },
            {
                "name": "Seated Forward Fold",
                "sets": "2 x 20s",
                "instructions": [
                    "Sit with legs straight out",
                    "Fold forward at hips",
                    "Reach toward toes, avoid rounding spine",
                    "Hold gently"
                ]
            },
            {
                "name": "Box Breathing",
                "sets": "5 rounds",
                "instructions": [
                    "Inhale for 4 counts",
                    "Hold for 4 counts",
                    "Exhale for 4 counts",
                    "Hold for 4 counts, repeat"
                ]
            },
        ]
    }
}

# ==============================
# Helpers
# ==============================
def get_workout_routine(day_index, time_of_day):
    """Return workout routine for a given day index (0–3) and time ('morning'/'night')."""
    day_key = f"day{day_index + 1}"
    return WORKOUTS.get(day_key, {}).get(time_of_day, [])

def workout_summary(routine):
    """Create formatted workout summary with instructions."""
    if not routine:
        return "Rest day — focus on recovery, stretching, and hydration."

    lines = []
    for ex in routine:
        lines.append(f"**{ex['name']}** — {ex['sets']}")
        for step in ex["instructions"]:
            lines.append(f"  • {step}")
        lines.append("")  # spacing
    return "\n".join(lines).strip()

def log_workout(user, time_of_day, routine):
    """Log completed workout to memory_log.txt."""
    if not routine:
        log_event(f"[WORKOUT] {user} rest day ({time_of_day})")
        return
    exercises = ", ".join([ex["name"] for ex in routine])
    log_event(f"[WORKOUT] {user} completed {time_of_day} workout: {exercises}")
