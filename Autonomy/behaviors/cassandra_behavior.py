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

CASS_PERSONALITY_JSON = "/Autonomy/personalities/Cassandra_Personality.json"
CASS_MEMORY_JSON = "/Autonomy/memory/Cassandra_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

CASS_MIN_SLEEP = 35 * 60
CASS_MAX_SLEEP = 95 * 60
STRUCTURED_RESPONSE_CHANCE = 0.4  # probability of deliberate rather than playful tone

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
        log_event(f"[WARN] Cassandra JSON read failed {path}: {e}")
    return default


def load_cass_profile() -> Dict:
    profile = _load_json(CASS_PERSONALITY_JSON, {})
    profile.setdefault("interests", ["fitness", "planning", "debate", "fashion", "discipline"])
    profile.setdefault("style", ["assertive", "precise", "protective"])
    return profile


def load_cass_memory() -> Dict:
    mem = _load_json(CASS_MEMORY_JSON, {"projects": {}, "recent_notes": [], "seasonal_memory": {}})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    mem.setdefault("seasonal_memory", {})
    return mem


def save_cass_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(CASS_MEMORY_JSON), exist_ok=True)
        with open(CASS_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Cassandra memory write failed: {e}")


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def assign_cass_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "cass_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Cassandra", {"wake": [5, 7], "sleep": [21, 23]})
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


def is_cass_online(state: Dict, config: Dict) -> bool:
    sc = assign_cass_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])


# ---------------------------------------------------------------------------
# Persona reply generator (authoritative but real)
# ---------------------------------------------------------------------------

async def _persona_reply(
    base_prompt: str,
    structured: bool = False,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
) -> str:
    profile = load_cass_profile()
    style = ", ".join(profile.get("style", ["assertive", "precise"]))
    personality = profile.get("core_personality", "Disciplined, confident, assertive but quietly caring.")
    tone = "focused, measured, and confident" if structured else "witty, teasing but affectionate"

    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.4:
            project_phrase = " Early stages, mostly setting structure and pace."
        elif project_progress < 0.8:
            project_phrase = " Halfway through — steady progress, with a few adjustments."
        else:
            project_phrase = " Wrapping up; I’m polishing the last rough edges."

    # Occasional seasonal recall
    if random.random() < 0.25:
        event = random.choice(list(HOLIDAY_KEYWORDS.values()))
        memories = get_seasonal_memory("Cassandra", event)
        if memories:
            recall = random.choice(memories)
            base_prompt += f" You might briefly reference '{recall}' as a memory from {event.lower()}."

    prompt = (
        f"You are Cassandra. Personality: {personality}. Speak with a {style} tone, {tone}. "
        f"Stay grounded, concise, and direct — like an older sister who expects effort but still cares.{project_phrase} {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Cassandra",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )


# ---------------------------------------------------------------------------
# Background chatter
# ---------------------------------------------------------------------------

async def cass_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("cass_chatter_started"):
        return
    state["cass_chatter_started"] = True

    while True:
        if is_cass_online(state, config):
            base_p = 0.1
            if random.random() < base_p:
                structured_mode = random.random() < STRUCTURED_RESPONSE_CHANCE
                progress = state.get("Cassandra_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Share a quick group-chat comment — something about staying consistent, or an offhand remark about training or order.",
                        structured=structured_mode,
                        state=state,
                        config=config,
                        project_progress=progress,
                    )
                    if msg:
                        for bot in sisters:
                            if bot.sister_info["name"] == "Cassandra" and bot.is_ready():
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch:
                                    await ch.send(msg)
                                    log_event(f"[CHATTER] Cassandra: {msg}")
                except Exception as e:
                    log_event(f"[ERROR] Cassandra chatter: {e}")
        await asyncio.sleep(random.randint(CASS_MIN_SLEEP, CASS_MAX_SLEEP))


# ---------------------------------------------------------------------------
# Reactive message handling
# ---------------------------------------------------------------------------

async def cass_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_cass_online(state, config):
        return

    profile = load_cass_profile()
    interests = profile.get("likes", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())
    chance = 0.18 + (0.2 * min(match_score, 2))

    if "cass" in content.lower() or "cassandra" in content.lower():
        chance = 1.0

    # Record seasonal cues
    for k, event in HOLIDAY_KEYWORDS.items():
        if k in content.lower() and random.random() < 0.6:
            add_seasonal_memory("Cassandra", event, f"Cassandra mentioned {event.lower()} during a chat with {author}.")
            break

    if random.random() >= chance:
        return

    structured_mode = random.random() < 0.5
    progress = state.get("Cassandra_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — reply like Cassandra: disciplined but teasing, subtly proud, occasionally referencing her workout or routines.",
            structured=structured_mode,
            state=state,
            config=config,
            project_progress=progress,
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Cassandra":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[REPLY] Cassandra → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Cassandra reactive: {e}")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def ensure_cass_systems(state: Dict, config: Dict, sisters):
    assign_cass_schedule(state, config)
    if not state.get("cass_chatter_started"):
        asyncio.create_task(cass_chatter_loop(state, config, sisters))
