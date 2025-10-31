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

IVY_PERSONALITY_JSON = "/Autonomy/personalities/Ivy_Personality.json"
IVY_MEMORY_JSON = "/Autonomy/memory/Ivy_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

IVY_MIN_SLEEP = 45 * 60
IVY_MAX_SLEEP = 110 * 60
TEASING_RESPONSE_CHANCE = 0.45  # % chance of playful tone instead of sincere

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
        log_event(f"[WARN] Ivy JSON read failed {path}: {e}")
    return default


def load_ivy_profile() -> Dict:
    profile = _load_json(IVY_PERSONALITY_JSON, {})
    profile.setdefault("interests", ["fashion", "makeup", "mechanics", "music", "mischief"])
    profile.setdefault("style", ["flirty", "sarcastic", "chaotic good"])
    return profile


def load_ivy_memory() -> Dict:
    mem = _load_json(IVY_MEMORY_JSON, {"projects": {}, "recent_notes": [], "seasonal_memory": {}})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    mem.setdefault("seasonal_memory", {})
    return mem


def save_ivy_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(IVY_MEMORY_JSON), exist_ok=True)
        with open(IVY_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Ivy memory write failed: {e}")


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def assign_ivy_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "ivy_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Ivy", {"wake": [9, 11], "sleep": [0, 2]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        if lo > hi:
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


def is_ivy_online(state: Dict, config: Dict) -> bool:
    sc = assign_ivy_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])


# ---------------------------------------------------------------------------
# Persona reply generator (chaotic but sincere)
# ---------------------------------------------------------------------------

async def _persona_reply(
    base_prompt: str,
    teasing: bool = False,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
) -> str:
    profile = load_ivy_profile()
    style = ", ".join(profile.get("style", ["flirty", "chaotic good"]))
    personality = profile.get("core_personality", "Playful, teasing, creative troublemaker with hidden warmth.")
    tone = "mischievous, light-hearted, and slightly dramatic" if teasing else "genuine, warm, and a bit vulnerable"

    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.4:
            project_phrase = " I started something new — might break it just to rebuild it better."
        elif project_progress < 0.8:
            project_phrase = " It’s coming along — somehow it’s messier but prettier."
        else:
            project_phrase = " I actually finished it, and shockingly, it didn’t explode."

    # Occasional seasonal recall
    if random.random() < 0.3:
        event = random.choice(list(HOLIDAY_KEYWORDS.values()))
        memories = get_seasonal_memory("Ivy", event)
        if memories:
            recall = random.choice(memories)
            base_prompt += f" Maybe slip in a cheeky line about '{recall}' from {event.lower()}."

    prompt = (
        f"You are Ivy. Personality: {personality}. Speak with a {style} tone, {tone}. "
        f"Keep it natural, teasing but affectionate, and occasionally show your clever side.{project_phrase} {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Ivy",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )


# ---------------------------------------------------------------------------
# Background chatter
# ---------------------------------------------------------------------------

async def ivy_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("ivy_chatter_started"):
        return
    state["ivy_chatter_started"] = True

    while True:
        if is_ivy_online(state, config):
            base_p = 0.12
            if random.random() < base_p:
                teasing_mode = random.random() < TEASING_RESPONSE_CHANCE
                progress = state.get("Ivy_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Say something quick and funny in chat — maybe a playful tease, or something oddly insightful.",
                        teasing=teasing_mode,
                        state=state,
                        config=config,
                        project_progress=progress,
                    )
                    if msg:
                        for bot in sisters:
                            if bot.sister_info["name"] == "Ivy" and bot.is_ready():
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch:
                                    await ch.send(msg)
                                    log_event(f"[CHATTER] Ivy: {msg}")
                except Exception as e:
                    log_event(f"[ERROR] Ivy chatter: {e}")
        await asyncio.sleep(random.randint(IVY_MIN_SLEEP, IVY_MAX_SLEEP))


# ---------------------------------------------------------------------------
# Reactive message handling
# ---------------------------------------------------------------------------

async def ivy_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_ivy_online(state, config):
        return

    profile = load_ivy_profile()
    interests = profile.get("likes", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())
    chance = 0.25 + (0.2 * min(match_score, 2))

    if "ivy" in content.lower():
        chance = 1.0

    # Track seasonal chatter
    for k, event in HOLIDAY_KEYWORDS.items():
        if k in content.lower() and random.random() < 0.6:
            add_seasonal_memory("Ivy", event, f"Ivy joked about {event.lower()} with {author}.")
            break

    if random.random() >= chance:
        return

    teasing_mode = random.random() < 0.6
    progress = state.get("Ivy_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — reply like Ivy: teasing, lively, a little bratty but clearly affectionate.",
            teasing=teasing_mode,
            state=state,
            config=config,
            project_progress=progress,
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Ivy":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[REPLY] Ivy → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Ivy reactive: {e}")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def ensure_ivy_systems(state: Dict, config: Dict, sisters):
    assign_ivy_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(ivy_chatter_loop(state, config, sisters))
