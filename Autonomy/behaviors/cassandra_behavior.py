import os
import json
import random
import asyncio
from datetime import datetime
import pytz
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# ---------------------------------------------------------------------------
# Personality and memory paths
# ---------------------------------------------------------------------------
CASS_PERSONALITY_JSON = "/Autonomy/personalities/Cassandra_Personality.json"
CASS_MEMORY_JSON      = "/Autonomy/memory/Cassandra_Memory.json"

# ---------------------------------------------------------------------------
# Defaults / pacing
# ---------------------------------------------------------------------------
CASS_MIN_SLEEP = 40 * 60
CASS_MAX_SLEEP = 100 * 60
DISCIPLINE_BANTER_CHANCE = 0.25
DRY_HUMOR_CHANCE = 0.35

AEDT = pytz.timezone("Australia/Sydney")

# ---------------------------------------------------------------------------
# Unique media preferences (structured, stoic, gym-savvy but human)
# ---------------------------------------------------------------------------
REAL_MEDIA = {
    "games": [
        "Code Vein",
        "Dark Souls III",
        "NieR:Automata",
        "Monster Hunter World",
        "Ghost of Tsushima",
        "Celeste",
    ],
    "anime": [
        "Attack on Titan",
        "Kabaneri of the Iron Fortress",
        "Psycho-Pass",
        "Vinland Saga",
        "Ergo Proxy",
    ],
    "shows": [
        "Suits",
        "House",
        "The Rookie",
        "Sherlock",
        "The Expanse",
    ],
    "music": [
        "progressive metal",
        "symphonic rock",
        "orchestral game scores",
        "nerdcore",
        "drum and bass",
    ],
}

def preferred_media_category() -> str:
    """Cassandra gravitates toward powerful, focused energy — games or music."""
    return random.choice(["games", "music", "shows"])

# ---------------------------------------------------------------------------
# JSON helpers
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
    profile.setdefault("interests", ["training", "order", "strategy", "analysis"])
    profile.setdefault("style", ["commanding", "analytical", "dryly humorous"])
    profile.setdefault("core_personality", "Disciplined and blunt, but with dry humor and buried warmth.")
    return profile

def load_cass_memory() -> Dict:
    mem = _load_json(CASS_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_cass_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(CASS_MEMORY_JSON), exist_ok=True)
        with open(CASS_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Cassandra memory write failed: {e}")

# ---------------------------------------------------------------------------
# Schedule (AEDT)
# ---------------------------------------------------------------------------
def assign_cass_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key = "cass_schedule"
    kd  = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Cassandra", {"wake": [5, 7], "sleep": [21, 23]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        if hi <= lo:
            hi = lo + 1
        return random.randint(lo, hi)

    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key] = schedule
    state[kd]  = today
    return schedule

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep: return True
    if wake < sleep:  return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_cass_online(state: Dict, config: Dict) -> bool:
    sc = assign_cass_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------------------------------------------------------------------------
# Persona reply generator
# ---------------------------------------------------------------------------
async def _persona_reply(
    base_prompt: str,
    dry: bool = False,
    disciplined: bool = False,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
    media_mention: Optional[str] = None,
) -> str:
    profile = load_cass_profile()
    style = ", ".join(profile.get("style", ["commanding", "analytical"]))
    personality = profile.get(
        "core_personality",
        "Disciplined and blunt, but with dry humor and buried warmth."
    )

    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.3:
            project_phrase = " Just started — laying the groundwork."
        elif project_progress < 0.7:
            project_phrase = " Midway through — tightening things up."
        else:
            project_phrase = " Nearly done — precision adjustments left."

    humor = "dry and understated" if dry else "sharp but subtle"
    tone = "structured, direct, yet quietly kind" if disciplined else "relaxed and observant"
    media_clause = f" You may mention {media_mention} naturally if it fits." if media_mention else ""

    prompt = (
        f"You are Cassandra. Personality: {personality}. Speak in a {style} tone, "
        f"{tone}, with {humor} humor. {project_phrase}{media_clause} "
        f"Keep replies concise (1–2 sentences), realistic, and grounded in sibling banter. {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Cassandra",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------------------------------------------------------------------
# Background chatter loop
# ---------------------------------------------------------------------------
async def cass_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("cass_chatter_started"):
        return
    state["cass_chatter_started"] = True

    while True:
        if is_cass_online(state, config):
            base_p = 0.09  # measured but steady presence
            if random.random() < base_p:
                progress = state.get("Cassandra_project_progress", random.random())
                media_choice = random.choice(REAL_MEDIA.get(preferred_media_category(), []))
                try:
                    msg = await _persona_reply(
                        "Say something sharp or reflective — a practical observation or light tease toward a sibling.",
                        dry=(random.random() < DRY_HUMOR_CHANCE),
                        disciplined=(random.random() < DISCIPLINE_BANTER_CHANCE),
                        state=state,
                        config=config,
                        project_progress=progress,
                        media_mention=media_choice if random.random() < 0.5 else None,
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
# Reactive handler
# ---------------------------------------------------------------------------
async def cass_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_cass_online(state, config):
        return

    profile = load_cass_profile()
    interests = profile.get("interests", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())
    chance = 0.15 + (0.25 * min(match_score, 2))

    if "cass" in content.lower() or "cassandra" in content.lower():
        chance = 1.0

    if random.random() >= min(1.0, chance):
        return

    progress = state.get("Cassandra_project_progress", random.random())
    media_choice = random.choice(REAL_MEDIA.get(preferred_media_category(), []))

    try:
        reply = await _persona_reply(
            f'{author} said: "{content}" — respond in a way that’s pragmatic, teasing, or quietly approving.',
            dry=(random.random() < 0.4),
            disciplined=(random.random() < 0.5),
            state=state,
            config=config,
            project_progress=progress,
            media_mention=media_choice if random.random() < 0.4 else None,
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
# Startup hook
# ---------------------------------------------------------------------------
def ensure_cass_systems(state: Dict, config: Dict, sisters):
    assign_cass_schedule(state, config)
    if not state.get("cass_chatter_started"):
        asyncio.create_task(cass_chatter_loop(state, config, sisters))
