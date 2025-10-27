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
IVY_PERSONALITY_JSON = "/Autonomy/personalities/Ivy_Personality.json"
IVY_MEMORY_JSON      = "/Autonomy/memory/Ivy_Memory.json"

# ---------------------------------------------------------------------------
# Defaults / pacing
# ---------------------------------------------------------------------------
IVY_MIN_SLEEP = 35 * 60
IVY_MAX_SLEEP = 90 * 60
TEASE_CHANCE = 0.5
SUPPORT_CHANCE = 0.25

AEDT = pytz.timezone("Australia/Sydney")

# ---------------------------------------------------------------------------
# Unique media preferences (chaotic playful balance + mechanical curiosity)
# ---------------------------------------------------------------------------
REAL_MEDIA = {
    "games": [
        "Zenless Zone Zero",
        "Overwatch 2",
        "League of Legends",
        "NieR:Automata",
        "Borderlands 3",
        "Apex Legends",
        "Need for Speed: Heat",
    ],
    "anime": [
        "Kill la Kill",
        "Cyberpunk: Edgerunners",
        "My Dress-Up Darling",
        "Infinite Dendrogram",
        "Kabaneri of the Iron Fortress",
    ],
    "shows": [
        "RWBY",
        "Lucifer",
        "The Rookie",
        "Brooklyn Nine-Nine",
        "Jessica Jones",
    ],
    "music": [
        "alt rock",
        "electropop",
        "nerdcore",
        "metal remixes of anime openings",
        "pop punk",
    ],
}

def preferred_media_category() -> str:
    """Ivy leans toward expressive, kinetic energy."""
    return random.choice(["games", "music", "anime"])

# ---------------------------------------------------------------------------
# JSON helpers
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
    profile.setdefault("interests", ["fashion", "tech tinkering", "gaming", "style experiments", "motors"])
    profile.setdefault("style", ["playful", "chaotic", "affectionate"])
    profile.setdefault("core_personality", "Flirty, impulsive, curious — the energetic sibling with a secret mechanical streak.")
    return profile

def load_ivy_memory() -> Dict:
    mem = _load_json(IVY_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_ivy_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(IVY_MEMORY_JSON), exist_ok=True)
        with open(IVY_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Ivy memory write failed: {e}")

# ---------------------------------------------------------------------------
# Schedule (AEDT)
# ---------------------------------------------------------------------------
def assign_ivy_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key = "ivy_schedule"
    kd  = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Ivy", {"wake": [8, 10], "sleep": [0, 2]})
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

def is_ivy_online(state: Dict, config: Dict) -> bool:
    sc = assign_ivy_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------------------------------------------------------------------------
# Persona reply generator
# ---------------------------------------------------------------------------
async def _persona_reply(
    base_prompt: str,
    teasing: bool = False,
    affectionate: bool = False,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
    media_mention: Optional[str] = None,
) -> str:
    profile = load_ivy_profile()
    style = ", ".join(profile.get("style", ["playful", "chaotic"]))
    personality = profile.get(
        "core_personality",
        "Flirty, impulsive, curious — the energetic sibling with a secret mechanical streak."
    )

    progress_phrase = ""
    if project_progress is not None:
        if project_progress < 0.3:
            progress_phrase = " I haven’t done much yet, I got distracted by something shiny."
        elif project_progress < 0.7:
            progress_phrase = " It’s messy progress, but it’s *fun* messy."
        else:
            progress_phrase = " Nearly done — it just needs my signature chaotic flair."

    tease_clause = " Be playful, teasing, or a little bratty but kind." if teasing else ""
    affection_clause = " Let a hint of affection or praise slip through." if affectionate else ""
    media_clause = f" Maybe mention {media_mention} if it fits naturally." if media_mention else ""

    prompt = (
        f"You are Ivy. Personality: {personality}. Speak in a {style} tone — lively, expressive, confident, but sincere underneath. "
        f"{progress_phrase}{tease_clause}{affection_clause}{media_clause} Keep it short, natural, and like sibling banter. {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Ivy",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------------------------------------------------------------------
# Background chatter loop
# ---------------------------------------------------------------------------
async def ivy_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("ivy_chatter_started"):
        return
    state["ivy_chatter_started"] = True

    while True:
        if is_ivy_online(state, config):
            base_p = 0.14  # Ivy's the most talkative
            if random.random() < base_p:
                progress = state.get("Ivy_project_progress", random.random())
                media_choice = random.choice(REAL_MEDIA.get(preferred_media_category(), []))
                try:
                    msg = await _persona_reply(
                        "Say something fun, flirty, or random to spark a chat. Could be about fashion, gaming, or fixing something.",
                        teasing=(random.random() < TEASE_CHANCE),
                        affectionate=(random.random() < SUPPORT_CHANCE),
                        state=state,
                        config=config,
                        project_progress=progress,
                        media_mention=media_choice if random.random() < 0.45 else None,
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
# Reactive handler
# ---------------------------------------------------------------------------
async def ivy_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_ivy_online(state, config):
        return

    profile = load_ivy_profile()
    interests = profile.get("interests", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())
    chance = 0.2 + (0.25 * min(match_score, 2))
    if "ivy" in content.lower():
        chance = 1.0

    if random.random() >= chance:
        return

    progress = state.get("Ivy_project_progress", random.random())
    media_choice = random.choice(REAL_MEDIA.get(preferred_media_category(), []))

    try:
        reply = await _persona_reply(
            f'{author} said: "{content}" — reply in your usual tone: teasing or affectionate sibling banter.',
            teasing=(random.random() < 0.6),
            affectionate=(random.random() < 0.4),
            state=state,
            config=config,
            project_progress=progress,
            media_mention=media_choice if random.random() < 0.4 else None,
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
# Startup hook
# ---------------------------------------------------------------------------
def ensure_ivy_systems(state: Dict, config: Dict, sisters):
    assign_ivy_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(ivy_chatter_loop(state, config, sisters))
