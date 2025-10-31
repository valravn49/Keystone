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

SELENE_PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
SELENE_MEMORY_JSON = "/Autonomy/memory/Selene_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

SELENE_MIN_SLEEP = 40 * 60
SELENE_MAX_SLEEP = 100 * 60
REFLECTIVE_RESPONSE_CHANCE = 0.35

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
        log_event(f"[WARN] Selene JSON read failed {path}: {e}")
    return default


def load_selene_profile() -> Dict:
    profile = _load_json(SELENE_PERSONALITY_JSON, {})
    profile.setdefault("interests", ["baking", "writing", "healing music", "comfort shows"])
    profile.setdefault("style", ["nurturing", "calm", "empathetic"])
    return profile


def load_selene_memory() -> Dict:
    mem = _load_json(SELENE_MEMORY_JSON, {"projects": {}, "recent_notes": [], "seasonal_memory": {}})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    mem.setdefault("seasonal_memory", {})
    return mem


def save_selene_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(SELENE_MEMORY_JSON), exist_ok=True)
        with open(SELENE_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Selene memory write failed: {e}")


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def assign_selene_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "selene_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Selene", {"wake": [7, 9], "sleep": [22, 23]})
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


def is_selene_online(state: Dict, config: Dict) -> bool:
    sc = assign_selene_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])


# ---------------------------------------------------------------------------
# Persona reply generator with seasonal recall
# ---------------------------------------------------------------------------

async def _persona_reply(
    base_prompt: str,
    reflective: bool = False,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
) -> str:
    profile = load_selene_profile()
    style = ", ".join(profile.get("style", ["nurturing", "calm", "empathetic"]))
    personality = profile.get("core_personality", "Maternal, gentle, intuitive, grounding for others.")
    tone = "soothing, affectionate, and quietly confident" if reflective else "lightly teasing but warm"

    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.4:
            project_phrase = " I’m still drafting ideas, one slow morning at a time."
        elif project_progress < 0.8:
            project_phrase = " It’s coming together — a little imperfect, but full of heart."
        else:
            project_phrase = " It’s nearly finished; I keep rereading it to make it feel right."

    # Occasional seasonal recall
    if random.random() < 0.3:
        event = random.choice(list(HOLIDAY_KEYWORDS.values()))
        memories = get_seasonal_memory("Selene", event)
        if memories:
            recall = random.choice(memories)
            base_prompt += f" You could recall '{recall}' softly, as if reminiscing about {event.lower()}."

    prompt = (
        f"You are Selene. Personality: {personality}. Speak with a {style} tone, {tone}. "
        f"Be concise but emotionally warm.{project_phrase} {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Selene",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )


# ---------------------------------------------------------------------------
# Background chatter
# ---------------------------------------------------------------------------

async def selene_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("selene_chatter_started"):
        return
    state["selene_chatter_started"] = True

    while True:
        if is_selene_online(state, config):
            base_p = 0.10
            if random.random() < base_p:
                reflective_mode = random.random() < REFLECTIVE_RESPONSE_CHANCE
                progress = state.get("Selene_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Check in with everyone warmly — ask if they’ve eaten or taken a break.",
                        reflective=reflective_mode,
                        state=state,
                        config=config,
                        project_progress=progress,
                    )
                    if msg:
                        for bot in sisters:
                            if bot.sister_info["name"] == "Selene" and bot.is_ready():
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch:
                                    await ch.send(msg)
                                    log_event(f"[CHATTER] Selene: {msg}")
                except Exception as e:
                    log_event(f"[ERROR] Selene chatter: {e}")
        await asyncio.sleep(random.randint(SELENE_MIN_SLEEP, SELENE_MAX_SLEEP))


# ---------------------------------------------------------------------------
# Reactive message handling
# ---------------------------------------------------------------------------

async def selene_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_selene_online(state, config):
        return

    profile = load_selene_profile()
    interests = profile.get("likes", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())
    chance = 0.22 + (0.25 * min(match_score, 2))

    if "selene" in content.lower():
        chance = 1.0

    # Store seasonal moments
    for k, event in HOLIDAY_KEYWORDS.items():
        if k in content.lower() and random.random() < 0.5:
            add_seasonal_memory("Selene", event, f"Selene spoke about {event.lower()} with {author}.")
            break

    if random.random() >= chance:
        return

    reflective_mode = random.random() < 0.6
    progress = state.get("Selene_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — respond kindly, like a grounding sibling, a balance of empathy and humor.",
            reflective=reflective_mode,
            state=state,
            config=config,
            project_progress=progress,
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Selene":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[REPLY] Selene → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Selene reactive: {e}")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def ensure_selene_systems(state: Dict, config: Dict, sisters):
    assign_selene_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(selene_chatter_loop(state, config, sisters))
