import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional
import pytz

from llm import generate_llm_reply
from logger import log_event
from Autonomy.behaviors.memory_helpers import get_seasonal_memory, add_seasonal_memory

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

ARIA_PERSONALITY_JSON = "/Autonomy/personalities/Aria_Personality.json"
ARIA_MEMORY_JSON = "/Autonomy/memory/Aria_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

ARIA_MIN_SLEEP = 45 * 60
ARIA_MAX_SLEEP = 110 * 60
THOUGHTFUL_RESPONSE_CHANCE = 0.25

HOLIDAY_KEYWORDS = {
    "halloween": "Halloween",
    "christmas": "Christmas",
    "new year": "New Year",
    "valentine": "Valentine's Day",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Aria JSON read failed {path}: {e}")
    return default


def load_aria_profile() -> Dict:
    profile = _load_json(ARIA_PERSONALITY_JSON, {})
    profile.setdefault("interests", ["organization", "craft", "electronics", "books"])
    profile.setdefault("style", ["structured", "gentle", "reflective"])
    return profile


def load_aria_memory() -> Dict:
    mem = _load_json(ARIA_MEMORY_JSON, {"projects": {}, "recent_notes": [], "seasonal_memory": {}})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    mem.setdefault("seasonal_memory", {})
    return mem


def save_aria_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(ARIA_MEMORY_JSON), exist_ok=True)
        with open(ARIA_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Aria memory write failed: {e}")


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def assign_aria_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "aria_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Aria", {"wake": [6, 8], "sleep": [22, 23]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        if lo > hi:  # handle wrap-around times
            hi += 24
        val = random.randint(lo, hi)
        return val if val < 24 else val - 24
    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key] = schedule
    state[kd] = today
    return schedule


def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep:
        return True
    if wake < sleep:
        return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep


def is_aria_online(state: Dict, config: Dict) -> bool:
    sc = assign_aria_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])


# ---------------------------------------------------------------------------
# Persona reply generator with seasonal memory recall
# ---------------------------------------------------------------------------

async def _persona_reply(
    base_prompt: str,
    reflective: bool = False,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
) -> str:
    profile = load_aria_profile()
    style = ", ".join(profile.get("style", ["structured", "gentle"]))
    personality = profile.get("core_personality", "Calm, methodical, detail-oriented but warm.")
    tone = "quietly thoughtful and deliberate" if reflective else "soft, concise, and lightly teasing"

    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.4:
            project_phrase = " My project’s still early, just sketching ideas out."
        elif project_progress < 0.8:
            project_phrase = " It’s coming together piece by piece — slow, but neat."
        else:
            project_phrase = " Almost done; I keep adjusting the smallest details."

    # 25% chance of seasonal memory recall
    if random.random() < 0.25:
        event = random.choice(list(HOLIDAY_KEYWORDS.values()))
        memories = get_seasonal_memory("Aria", event)
        if memories:
            recall = random.choice(memories)
            base_prompt += f" Maybe recall '{recall}' as if reminiscing naturally about {event.lower()}."

    prompt = (
        f"You are Aria. Personality: {personality}. Speak with a {style} tone, {tone}. "
        f"Keep it minimal, warm, and realistic.{project_phrase} {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Aria",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )


# ---------------------------------------------------------------------------
# Background chatter loop
# ---------------------------------------------------------------------------

async def aria_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("aria_chatter_started"):
        return
    state["aria_chatter_started"] = True

    while True:
        if is_aria_online(state, config):
            base_p = 0.08
            if random.random() < base_p:
                reflective_mode = random.random() < THOUGHTFUL_RESPONSE_CHANCE
                progress = state.get("Aria_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Share a calm group-chat comment — something practical or gently observant.",
                        reflective=reflective_mode,
                        state=state,
                        config=config,
                        project_progress=progress,
                    )
                    if msg:
                        for bot in sisters:
                            if bot.sister_info["name"] == "Aria" and bot.is_ready():
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch:
                                    await ch.send(msg)
                                    log_event(f"[CHATTER] Aria: {msg}")
                except Exception as e:
                    log_event(f"[ERROR] Aria chatter: {e}")
        await asyncio.sleep(random.randint(ARIA_MIN_SLEEP, ARIA_MAX_SLEEP))


# ---------------------------------------------------------------------------
# Reactive handler (conversation-level)
# ---------------------------------------------------------------------------

async def aria_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_aria_online(state, config):
        return

    profile = load_aria_profile()
    interests = profile.get("likes", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())

    chance = 0.18 + (0.2 * min(match_score, 2))
    if "aria" in content.lower():
        chance = 1.0

    # Detect seasonal keyword and store memory
    for k, event in HOLIDAY_KEYWORDS.items():
        if k in content.lower() and random.random() < 0.5:
            add_seasonal_memory("Aria", event, f"Aria talked about {event.lower()} with {author}.")
            break

    if random.random() >= chance:
        return

    reflective_mode = random.random() < 0.5
    progress = state.get("Aria_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — respond naturally, patient but playful, like a steady older sister.",
            reflective=reflective_mode,
            state=state,
            config=config,
            project_progress=progress,
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Aria":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[REPLY] Aria → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Aria reactive: {e}")


# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------

def ensure_aria_systems(state: Dict, config: Dict, sisters):
    assign_aria_schedule(state, config)
    if not state.get("aria_chatter_started"):
        asyncio.create_task(aria_chatter_loop(state, config, sisters))
