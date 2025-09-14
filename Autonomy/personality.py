import os
import json
import random
from datetime import datetime

PERSONALITY_DIR = "personalities"

class PersonalityManager:
    def __init__(self, name: str):
        self.name = name
        self.file = os.path.join(PERSONALITY_DIR, f"{name.lower()}.json")
        self.data = self._load()

    def _load(self):
        if not os.path.exists(self.file):
            raise FileNotFoundError(f"[PERSONALITY] No file found for {self.name} at {self.file}")
        with open(self.file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        print(f"[PERSONALITY] {self.name} personality saved.")

    def describe(self):
        return self.data.get("base", "")

    def drift(self):
        """
        Apply weighted drift to growth_path traits.
        Some traits strengthen, others regress.
        """
        changed = {}
        for trait, value in self.data["growth_path"].items():
            bias = self.data["drift_bias"].get(trait, 1.0)
            step = random.uniform(-0.05, 0.05) * bias
            new_val = max(0.0, min(1.0, value + step))
            self.data["growth_path"][trait] = new_val
            changed[trait] = round(new_val, 3)

        self.data["last_drift"] = datetime.utcnow().isoformat()
        self.save()
        return changed
