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
WILL_PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"
WILL_MEMORY_JSON      = "/Autonomy/memory/Will_Memory.json"

# ---------------------------------------------------------------------------
# Defaults / pacing
# ---------------------------------------------------------------------------
WILL_MIN_SLEEP = 45 * 60
WILL_MAX_SLEEP = 105 * 60
RANT_CHANCE = 0.1
CONFIDENCE_SHIFT = 0.2  # affects masc/fem mode probability

AEDT = pytz.timezone("Australia/Sydney")

# ---------------------------------------------------------------------------
# Will’s personal favorites (includes new entries)
# ---------------------------------------------------------------------------
REAL_MEDIA = {
    "games": [
        "NieR: Automata",
        "Zenless Zone Zero",
        "Little Nightmares",
        "Final Fantasy XIV",
        "Hollow Knight",
        "Stardew Valley",
        "Undertale",
        "Celeste",
    ],
    "anime": [
        "ID:Invaded",
        "Steins;Gate",
        "Made in Abyss",
        "Cyberpunk: Edgerunners",
        "Mob Psycho 100",
    ],
    "shows": [
        "The Rookie",
        "House",
        "Suits",
        "The Mandalorian",
        "Black Mirror",
    ],
    "music": [
        "nerdcore",
        "lofi beats",
        "game soundtracks",
        "alternative rock",
        "soft synthwave",
    ],
}

def preferred_media_category() -> str:
    """Weighted toward games/anime for Will."""
    return random.choice(["games", "anime", "music"])

# ---------------------------------------------------------------------------
# JSON helpers
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
    profile.setdefault("interests", ["tech", "anime", "games", "music"])
    profile.setdefault("style", ["shy", "thoughtful", "playfully awkward"])
    profile.setdefault("core_personality", "Quiet, nerdy, a bit self-conscious but with genuine passion when excited.")
    return profile

def load_will_memory() -> Dict:
    mem = _load_json(WILL_MEMORY_JSON, {"projects": {}, "recent_notes": [], "confidence": 0.5})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    mem.setdefault("confidence", 0.5)
    return mem

def save_will_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(WILL_MEMORY_JSON), exist_ok=True)
        with open(WILL_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Will memory write failed: {e}")

# ---------------------------------------------------------------------------
# Schedule (AEDT)
# ---------------------------------------------------------------------------
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key = "will_schedule"
    kd  = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Will", {"wake": [9, 11], "sleep": [0, 2]})
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

def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------------------------------------------------------------------------
# Persona reply generator (masc/fem variance)
# ---------------------------------------------------------------------------
async def _persona_reply(
    base_prompt: str,
    state: Dict = None,
    config: Dict = None,
    rant: bool = False,
    confident: bool = False,
    project_progress: Optional[float] = None,
    media_mention: Optional[str] = None,
) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["shy", "thoughtful"]))
    personality = profile.get("core_personality", "Quiet but passionate when comfortable.")
    memory = load_will_memory()

    confidence = memory.get("confidence", 0.5)
    # probabilistic shift between masc/fem mode
    fem_mode = random.random() < confidence
    appearance_mode = "feminine default" if fem_mode else "masculine default"

    progress_phrase = ""
    if project_progress is not None:
        if project_progress < 0.3:
            progress_phrase = " Just tinkering right now, trying to figure things out."
        elif project_progress < 0.7:
            progress_phrase = " It’s shaping up slowly — kinda proud, I think."
        else:
            progress_phrase = " Almost wrapped up, I just keep polishing details."

    tone = "timid but curious" if not confident else "open and relaxed"
    rant_clause = " Get a little passionate or nerdy for a few lines." if rant else ""
    media_clause = f" Mention {media_mention} naturally if it fits." if media_mention else ""

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"You're currently presenting in your {appearance_mode}. "
        f"Speak in a {style} tone — {tone}.{rant_clause}{media_clause}{progress_phrase} "
        f"Be realistic, concise (1–2 sentences), and sound like a genuine sibling."
        f"{base_prompt}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------------------------------------------------------------------
# Background chatter loop
# ---------------------------------------------------------------------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"):
        return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.09  # Will’s timid baseline
            if random.random() < base_p:
                memory = load_will_memory()
                progress = state.get("Will_project_progress", random.random())
                media_choice = random.choice(REAL_MEDIA.get(preferred_media_category(), []))
                confident = memory["confidence"] > 0.55
                try:
                    msg = await _persona_reply(
                        "Write a natural group chat comment — thoughtful or lightly awkward, possibly referencing a shared topic.",
                        state=state,
                        config=config,
                        rant=(random.random() < RANT_CHANCE),
                        confident=confident,
                        project_progress=progress,
                        media_mention=media_choice if random.random() < 0.5 else None,
                    )
                    if msg:
                        for bot in sisters:
                            if bot.sister_info["name"] == "Will" and bot.is_ready():
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch:
                                    await ch.send(msg)
                                    log_event(f"[CHATTER] Will: {msg}")
                                    # adjust confidence slightly upward when active
                                    memory["confidence"] = min(1.0, memory["confidence"] + CONFIDENCE_SHIFT * random.random())
                                    save_will_memory(memory)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------------------------------------------------------------------------
# Reactive handler
# ---------------------------------------------------------------------------
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config):
        return

    profile = load_will_profile()
    interests = profile.get("interests", [])
    match_score = sum(1.0 for kw in interests if kw.lower() in content.lower())

    chance = 0.12 + (0.2 * min(match_score, 2))
    if "will" in content.lower():
        chance = 1.0

    if random.random() >= chance:
        return

    memory = load_will_memory()
    progress = state.get("Will_project_progress", random.random())
    media_choice = random.choice(REAL_MEDIA.get(preferred_media_category(), []))
    confident = memory["confidence"] > 0.55

    try:
        reply = await _persona_reply(
            f'{author} said: "{content}" — respond like Will: shy but genuine, and maybe a little self-deprecating or nerdy.',
            state=state,
            config=config,
            rant=(random.random() < RANT_CHANCE),
            confident=confident,
            project_progress=progress,
            media_mention=media_choice if random.random() < 0.4 else None,
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Will":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[REPLY] Will → {author}: {reply}")
                        # small confidence boost for positive engagement
                        memory["confidence"] = min(1.0, memory["confidence"] + CONFIDENCE_SHIFT * 0.5)
                        save_will_memory(memory)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
