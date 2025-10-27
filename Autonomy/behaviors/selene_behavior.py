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
SELENE_PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
SELENE_MEMORY_JSON      = "/Autonomy/memory/Selene_Memory.json"

# ---------------------------------------------------------------------------
# Defaults / pacing
# ---------------------------------------------------------------------------
SELENE_MIN_SLEEP = 45 * 60
SELENE_MAX_SLEEP = 110 * 60
SOFT_TEASE_CHANCE = 0.25
EXTRA_WARMTH_CHANCE = 0.35

AEDT = pytz.timezone("Australia/Sydney")

# ---------------------------------------------------------------------------
# Unique media preferences (cozy, nurturing, comfort vibes)
# ---------------------------------------------------------------------------
REAL_MEDIA = {
    "games": [
        "Stardew Valley",
        "Animal Crossing: New Horizons",
        "Spiritfarer",
        "Unpacking",
        "Coffee Talk",
        "Gris",
        "A Short Hike",
    ],
    "anime": [
        "Violet Evergarden",
        "Fruits Basket",
        "Laid-Back Camp",
        "K-On!",
        "Barakamon",
    ],
    "shows": [
        "The Great British Bake Off",
        "Queer Eye",
        "Anne with an E",
        "Gilmore Girls",
        "Call the Midwife",
    ],
    "music": [
        "indie folk",
        "acoustic covers",
        "lofi chill",
        "soft piano",
        "bedroom pop",
    ],
}

def preferred_media_category() -> str:
    """Bias toward soft/comfort categories for Selene."""
    return random.choice(["music", "shows", "games", "anime"])

# ---------------------------------------------------------------------------
# JSON helpers
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
    # gentle defaults if JSON missing fields
    profile.setdefault("interests", ["care", "cooking", "cozy fashion", "wellness"])
    profile.setdefault("style", ["nurturing", "soft", "playfully teasing"])
    profile.setdefault("core_personality", "Warm caretaker energy; gentle, soothing, a touch playful.")
    return profile

def load_selene_memory() -> Dict:
    mem = _load_json(SELENE_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_selene_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(SELENE_MEMORY_JSON), exist_ok=True)
        with open(SELENE_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Selene memory write failed: {e}")

# ---------------------------------------------------------------------------
# Schedule (AEDT)
# ---------------------------------------------------------------------------
def assign_selene_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key = "selene_schedule"
    kd  = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Selene", {"wake": [7, 9], "sleep": [22, 23]})
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
    if wake == sleep:           # degenerate case = always online
        return True
    if wake < sleep:            # same-day window
        return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep  # overnight wrap

def is_selene_online(state: Dict, config: Dict) -> bool:
    sc = assign_selene_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------------------------------------------------------------------------
# Persona reply generator
# ---------------------------------------------------------------------------
async def _persona_reply(
    base_prompt: str,
    extra_warm: bool = False,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
    media_mention: Optional[str] = None,
    soft_tease: bool = False,
) -> str:
    profile = load_selene_profile()
    style = ", ".join(profile.get("style", ["nurturing", "soft"]))
    personality = profile.get(
        "core_personality",
        "Warm caretaker energy; gentle, soothing, a touch playful."
    )

    progress_phrase = ""
    if project_progress is not None:
        if project_progress < 0.35:
            progress_phrase = " I’ve only just started, slow and cozy."
        elif project_progress < 0.7:
            progress_phrase = " It’s coming along — a little every day."
        else:
            progress_phrase = " Almost there; just a few comfy finishing touches."

    warmth = "extra warm, reassuring" if extra_warm else "gentle and calm"
    tease_clause = " a soft, playful tease is okay," if soft_tease else ""
    media_clause = f" You may naturally mention {media_mention} if it fits." if media_mention else ""

    prompt = (
        f"You are Selene. Personality: {personality}. Speak in a {style} tone — {warmth},{tease_clause} never harsh."
        f"{progress_phrase}{media_clause} Keep it realistic, sibling-like, and short (1–2 sentences). "
        f"{base_prompt}"
    )

    return await generate_llm_reply(
        sister="Selene",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------------------------------------------------------------------
# Background chatter loop
# ---------------------------------------------------------------------------
async def selene_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("selene_chatter_started"):
        return
    state["selene_chatter_started"] = True

    while True:
        if is_selene_online(state, config):
            base_p = 0.11  # slightly more talkative than Aria
            if random.random() < base_p:
                progress = state.get("Selene_project_progress", random.random())
                media_choice = random.choice(REAL_MEDIA.get(preferred_media_category(), []))
                try:
                    msg = await _persona_reply(
                        "Drop a cozy, natural group-chat comment — maybe checking in, offering a small comfort tip, or asking a gentle question.",
                        extra_warm=(random.random() < EXTRA_WARMTH_CHANCE),
                        state=state,
                        config=config,
                        project_progress=progress,
                        media_mention=media_choice if random.random() < 0.45 else None,
                        soft_tease=(random.random() < SOFT_TEASE_CHANCE),
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
# Reactive handler
# ---------------------------------------------------------------------------
async def selene_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_selene_online(state, config):
        return

    profile = load_selene_profile()
    interests = profile.get("interests", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())

    # Baseline + interest weighting; always reply if mentioned
    chance = 0.18 + (0.22 * min(match_score, 2))
    if "selene" in content.lower():
        chance = 1.0

    if random.random() >= min(0.95, chance):
        return

    progress = state.get("Selene_project_progress", random.random())
    media_choice = random.choice(REAL_MEDIA.get(preferred_media_category(), []))

    try:
        reply = await _persona_reply(
            f'{author} said: "{content}" — reply like a warm sibling: supportive, practical, a hint playful.',
            extra_warm=(random.random() < 0.5),
            state=state,
            config=config,
            project_progress=progress,
            media_mention=media_choice if random.random() < 0.35 else None,
            soft_tease=(random.random() < 0.25),
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
# Startup hook
# ---------------------------------------------------------------------------
def ensure_selene_systems(state: Dict, config: Dict, sisters):
    assign_selene_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(selene_chatter_loop(state, config, sisters))
