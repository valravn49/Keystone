import json
import os

# Load config.json (if it exists)
CONFIG_PATHS = [
    "config.json",
    "/mnt/data/config.json",
]

config = None
for p in CONFIG_PATHS:
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            config = json.load(f)
            break

if config is None:
    # Fallback minimal config
    config = {
        "family_group_channel": 1234567890,  # replace with real Discord channel ID
        "rotation": [
            {"name": "Aria", "personality": "calm, bookish"},
            {"name": "Selene", "personality": "gentle, nurturing"},
            {"name": "Cassandra", "personality": "disciplined, commanding"},
            {"name": "Ivy", "personality": "mischievous, teasing"},
        ],
        "themes": ["growth", "discipline", "playfulness", "balance"],
        "schedules": {
            "Aria": {"wake": [6, 8], "sleep": [22, 23]},
            "Selene": {"wake": [7, 9], "sleep": [23, 0]},
            "Cassandra": {"wake": [5, 7], "sleep": [21, 22]},
            "Ivy": {"wake": [9, 11], "sleep": [0, 1]},
            "Will": {"wake": [10, 12], "sleep": [0, 2]},
        },
    }
