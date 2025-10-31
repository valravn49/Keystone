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

WILL_PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"
WILL_MEMORY_JSON = "/Autonomy/memory/Will_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

WILL_MIN_SLEEP = 60 * 60
WILL_MAX_SLEEP = 130 * 60

SHY_MODE_CHANCE = 0.7  # shy vs confident
RANT_CHANCE = 0.12     # small bursts of passion
FEM_MODE_CHANCE = 0.25  # days when he leans feminine

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
        log_event(f"[WARN] Will JSON read failed {path}: {e}")
    return default


def load_will_profile() -> Dict:
    profile = _load_json(WILL_PERSONALITY_JSON, {})
    profile.setdefault("interests", [
        "tech", "games", "anime", "music", "retro consoles", "VR", "cosplay"
    ])
    profile.setdefault("style", ["timid", "clever", "earnest", "genderfluid"])
    profile.setdefault("favorites", [
        "Nier: Automata", "Zenless Zone Zero", "Little Nightmares",
        "Hollow Knight", "Stardew Valley", "Code Vein", "Persona 5"
    ])
    return profile


def load_will_memory() -> Dict:
    mem = _load_json(WILL_MEMORY_JSON, {"projects": {}, "recent_notes": [], "seasonal_memory": {}})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    mem.setdefault("seasonal_memory", {})
    return mem


def save_will_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(WILL_MEMORY_JSON), exist_ok=True)
        with open(WILL_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Will memory write failed: {e}")


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "will_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
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


def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])


# ---------------------------------------------------------------------------
# Persona reply generator (shy/confident modes)
# ---------------------------------------------------------------------------

async def _persona_reply(
    base_prompt: str,
    rant: bool = False,
    shy: bool = True,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
) -> str:
    profile = load_will_profile()
    personality = profile.get("core_personality", "Shy, nerdy, creative; sometimes bold, often thoughtful.")
    style = ", ".join(profile.get("style", ["timid", "earnest"]))
    favorites = profile.get("favorites", [])
    tone = "soft-spoken, tentative but kind" if shy else "animated, confident, and a bit cheeky"

    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.4:
            project_phrase = " I’ve just started — still sorting through code and ideas."
        elif project_progress < 0.8:
            project_phrase = " Making progress — a few bugs, but it’s exciting."
        else:
            project_phrase = " Finally finished something that actually works."

    # Random feminine/masculine mood shift
    feminine_today = random.random() < FEM_MODE_CHANCE
    presentation = "feeling a little fem today — softer voice, maybe a skirt" if feminine_today else "in a comfy hoodie and jeans, feeling masc but relaxed"

    # Occasionally passionate rants
    if rant and random.random() < 0.7 and favorites:
        fav = random.choice(favorites)
        base_prompt += f" You could go off on a small tangent about {fav} — show excitement but stay grounded."

    # Occasional seasonal recall
    if random.random() < 0.25:
        event = random.choice(list(HOLIDAY_KEYWORDS.values()))
        memories = get_seasonal_memory("Will", event)
        if memories:
            recall = random.choice(memories)
            base_prompt += f" Optionally mention a brief memory like '{recall}' from {event.lower()}."

    prompt = (
        f"You are Will. Personality: {personality}. Style: {style}. "
        f"Speak in a {tone} tone, naturally nerdy but self-aware. "
        f"You're {presentation}.{project_phrase} {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="brother",
        history=[],
    )


# ---------------------------------------------------------------------------
# Background chatter
# ---------------------------------------------------------------------------

async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"):
        return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.1
            if random.random() < base_p:
                rant_mode = random.random() < RANT_CHANCE
                shy_mode = random.random() < SHY_MODE_CHANCE
                progress = state.get("Will_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Say something offhand in the family chat — could be thoughtful, or a tiny tech tangent.",
                        rant=rant_mode,
                        shy=shy_mode,
                        state=state,
                        config=config,
                        project_progress=progress,
                    )
                    if msg:
                        for bot in sisters:
                            if bot.sister_info["name"] == "Will" and bot.is_ready():
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch:
                                    await ch.send(msg)
                                    log_event(f"[CHATTER] Will: {msg}")
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))


# ---------------------------------------------------------------------------
# Reactive message handling
# ---------------------------------------------------------------------------

async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config):
        return

    profile = load_will_profile()
    interests = profile.get("interests", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())
    chance = 0.2 + (0.25 * min(match_score, 2))

    if "will" in content.lower():
        chance = 1.0

    # Track seasonal remarks
    for k, event in HOLIDAY_KEYWORDS.items():
        if k in content.lower() and random.random() < 0.6:
            add_seasonal_memory("Will", event, f"Will reminisced about {event.lower()} with {author}.")
            break

    if random.random() >= chance:
        return

    rant_mode = random.random() < RANT_CHANCE
    shy_mode = random.random() < SHY_MODE_CHANCE
    progress = state.get("Will_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — reply like Will: thoughtful, slightly awkward but endearing, maybe referencing tech or art.",
            rant=rant_mode,
            shy=shy_mode,
            state=state,
            config=config,
            project_progress=progress,
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Will":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[REPLY] Will → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
