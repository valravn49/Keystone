# human_likeness.py
# ------------------------------------------------------------
# Compact utilities to add human-like variability:
# 1) Mood drift & persistence
# 2) Project motivation tie-in
# 3) Relationship temperature
# 4) Situational (time-of-day) adaptation
# 5) Expressive micro-traits
# 6) Natural recovery curve
# 7) Prompt composition helper
#
# This module is deliberately dependency-light and *stateless*:
# - You pass in memory/persona/state as dicts
# - You pass save/load callables if you want persistence here
# - No imports from sisters_behavior / will_behavior to avoid loops
# ------------------------------------------------------------
from __future__ import annotations
import random
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable

# ---------- Defaults & helpers ----------

_DEFAULT_MOODS = ["happy", "irritated", "tired", "focused", "neutral"]

def _now_iso() -> str:
    return datetime.now().isoformat()

def _get(d: Dict, path: str, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def _set(d: Dict, path: str, value):
    cur = d
    keys = path.split(".")
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value

# ---------- 1) Mood drift ----------

def ensure_mood(memory: Dict):
    """Ensure the memory has a mood block."""
    mood = memory.setdefault("current_mood", {
        "type": "neutral",
        "intensity": 0.3,
        "last_update": _now_iso(),
    })
    memory.setdefault("previous_mood", "neutral")
    return mood

def update_mood(memory: Dict, chance: float = 0.25):
    """
    Randomly nudge mood for the day or on trigger.
    """
    ensure_mood(memory)
    if random.random() < chance:
        mood_type = random.choice(_DEFAULT_MOODS)
        intensity = round(random.uniform(0.2, 0.8), 2)
        memory["current_mood"]["type"] = mood_type
        memory["current_mood"]["intensity"] = intensity
        memory["current_mood"]["last_update"] = _now_iso()
    return memory

# ---------- 2) Mood persistence (carryover) ----------

def carryover_mood(memory: Dict, soften_from: str = "irritated", soften_to: str = "calm", soften_chance: float = 0.4):
    """
    Carry yesterday’s mood into today with a softening rule.
    """
    ensure_mood(memory)
    prev = memory.get("previous_mood", "neutral")
    cur = memory["current_mood"]["type"]

    # If yesterday was harsh, sometimes wake calmer
    if prev == soften_from and random.random() < soften_chance:
        memory["current_mood"]["type"] = soften_to
        memory["current_mood"]["intensity"] = round(max(0.2, memory["current_mood"].get("intensity", 0.3) - 0.2), 2)

    # Store carryover for next round
    memory["previous_mood"] = cur
    return memory

# ---------- 3) Project tie-in ----------

def pick_active_project(memory: Dict) -> Optional[str]:
    """
    Returns a random project key from memory, or None.
    Expected schema:
    memory["projects"] = {title: {"progress": float, "motivation": float, "emotion": str}}
    """
    projects = memory.get("projects") or {}
    if not projects:
        return None
    return random.choice(list(projects.keys()))

def nudge_project(memory: Dict, title: str, small_step: bool = True):
    pj = (memory.setdefault("projects", {})).setdefault(title, {"progress": 0.0, "motivation": 0.5, "emotion": "neutral"})
    delta = random.uniform(0.02, 0.08) if small_step else random.uniform(0.08, 0.18)
    pj["progress"] = round(max(0.0, min(1.0, pj["progress"] + delta)), 2)
    # Motivation coupling
    if pj["progress"] >= 0.99:
        pj["emotion"] = "relieved"
        pj["motivation"] = min(1.0, pj["motivation"] + 0.1)
    else:
        # Slightly randomize emotion around effort
        if random.random() < 0.3:
            pj["emotion"] = random.choice(["frustrated", "focused", "curious"])
    return memory

def describe_progress(progress: float) -> str:
    if progress >= 1.0:
        return "you actually finished it and feel quietly proud."
    elif progress >= 0.7:
        return "you’re almost done, just ironing out the last bits."
    elif progress >= 0.4:
        return "it’s coming along; you’ve got a decent chunk done."
    return "you barely started; it’s only the first steps."

# ---------- 4) Relationship temperature ----------

def rel_get(state: Dict, a: str, b: str) -> Dict[str, float]:
    rels = state.setdefault("relationships", {})
    key = f"{a}→{b}"
    return rels.setdefault(key, {"warmth": 0.5, "teasing": 0.3})

def rel_adjust(state: Dict, a: str, b: str, warmth: float = 0.0, teasing: float = 0.0, clamp: bool = True):
    r = rel_get(state, a, b)
    r["warmth"] += warmth
    r["teasing"] += teasing
    if clamp:
        r["warmth"] = max(0.0, min(1.0, r["warmth"]))
        r["teasing"] = max(0.0, min(1.0, r["teasing"]))
    return r

def rel_decay_daily(state: Dict, factor: float = 0.98):
    rels = state.setdefault("relationships", {})
    for key, r in rels.items():
        r["warmth"] = round(r["warmth"] * factor, 3)
        r["teasing"] = round(r["teasing"] * factor, 3)

# ---------- 5) Situational (time-of-day) mode weighting ----------

_CONTEXT_WEIGHTS = {
    "morning": {"support": 1.2, "story": 1.1, "tease": 0.9},
    "midday":  {"tease": 1.1, "challenge": 1.1, "support": 1.0},
    "night":   {"story": 1.3, "support": 1.05, "tease": 0.9},
}

def time_bucket(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    h = now.hour
    if 5 <= h < 12: return "morning"
    if 12 <= h < 18: return "midday"
    return "night"

def weight_modes_by_time(mode_probs: Dict[str, float], now: Optional[datetime] = None) -> Dict[str, float]:
    bucket = time_bucket(now)
    weights = _CONTEXT_WEIGHTS.get(bucket, {})
    adjusted = {}
    for mode, p in mode_probs.items():
        adjusted[mode] = p * weights.get(mode, 1.0)
    return adjusted

# ---------- 6) Expressive micro-traits ----------

def inject_micro_traits(text: str, persona: Dict, chance: float = 0.3) -> str:
    """
    persona may carry:
      persona["micro_traits"] = {"filler": [...], "emoji": [...]}
    """
    traits = persona.get("micro_traits") or {}
    if random.random() < chance and traits.get("filler"):
        text += (" " if not text.endswith((" ", "\n")) else "") + random.choice(traits["filler"])
    if random.random() < chance and traits.get("emoji"):
        text += (" " if not text.endswith((" ", "\n")) else "") + random.choice(traits["emoji"])
    return text

# ---------- 7) Recovery curve (nightly) ----------

def cool_down_mood(memory: Dict], step: float = 0.2):
    ensure_mood(memory)
    cur = memory["current_mood"]
    cur["intensity"] = max(0.0, round(cur.get("intensity", 0.3) - step, 2))
    if cur["intensity"] <= 0.1:
        cur["type"] = "neutral"
    return memory

# ---------- Prompt composition helper ----------

def compose_prompt_addons(
    speaker_name: str,
    persona: Dict,
    memory: Dict,
    address_to: Optional[str] = None,
    relationship_warmth: Optional[float] = None,
    add_project_hint: bool = False,
    media_hint: Optional[str] = None,
) -> str:
    """
    Returns a natural-language prompt fragment with:
      - current mood
      - relationship warmth
      - optional tiny project nudge
      - optional media reference
      - addressing hint
    Safe to append directly to your base prompt.
    """
    ensure_mood(memory)
    mood = memory["current_mood"]
    mood_clause = f" Current mood: {mood['type']} (subtle)."
    rel_clause = ""
    if relationship_warmth is not None:
        if relationship_warmth > 0.7:
            rel_clause = " You feel close to them; let a gentle affection slip through."
        elif relationship_warmth < 0.3:
            rel_clause = " You're a touch colder toward them right now."
    addr_clause = f" If it fits, address {address_to} directly." if address_to else ""
    media_clause = f" If natural, weave in '{media_hint}'." if media_hint else ""
    proj_clause = ""
    if add_project_hint:
        active = pick_active_project(memory)
        if active:
            prog = memory["projects"][active].get("progress", 0.0)
            proj_clause = f" Tiny project note: you're working on '{active}' and {describe_progress(prog)}"

    extra_style = ""
    # Optional micro-traits: just note for the model
    if persona.get("micro_traits"):
        extra_style = " Keep your personal rhythm: subtle fillers/emojis you tend to use."

    return f"{mood_clause}{rel_clause}{addr_clause}{media_clause}{proj_clause}{extra_style}"
