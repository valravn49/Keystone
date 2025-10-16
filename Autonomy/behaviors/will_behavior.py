import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WILL_PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"
WILL_MEMORY_JSON = "/Autonomy/memory/Will_Memory.json"

# ---------------------------------------------------------------------------
# Config & pacing
# ---------------------------------------------------------------------------
WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

RANT_CHANCE = 0.12
TIMID_BASE_PROB = 0.75
INTEREST_HIT_BOOST = 0.35
IVY_BOOST = 0.25

# ---------------------------------------------------------------------------
# Fallback favorites pool (includes new entries)
# ---------------------------------------------------------------------------
WILL_FAVORITES_POOL = [
    "The Legend of Zelda: Tears of the Kingdom",
    "Final Fantasy XIV",
    "Hades",
    "Stardew Valley",
    "Hollow Knight",
    "Elden Ring",
    "Nier: Automata",
    "Zenless Zone Zero",
    "Little Nightmares",
    "retro game consoles",
    "PC building",
    "VR headsets",
    "indie games",
    "soundtrack analysis videos",
    "concept art showcases"
]

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
    profile.setdefault("style", ["timid", "soft-spoken", "creative"])
    profile.setdefault("interests", ["games", "music", "storytelling", "art"])
    profile.setdefault("favorites", WILL_FAVORITES_POOL)
    return profile


def load_will_memory() -> Dict:
    mem = _load_json(WILL_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
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
    def pick(span): return random.randint(int(span[0]), int(span[1]))
    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key] = schedule; state[kd] = today
    return schedule


def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep:
        return True
    if wake < sleep:
        return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep


def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_h = datetime.now().hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------------------------------------------------------------------------
# Progress phrasing
# ---------------------------------------------------------------------------
PROGRESS_PHRASES = {
    "early": [
        "I barely started. Still… kinda fun figuring it out.",
        "I’ve got like one sketch done, but it’s something."
    ],
    "mid": [
        "It’s coming along — rough edges, but I like it.",
        "Halfway there, I think. It keeps changing on me."
    ],
    "late": [
        "Almost done. Just adding polish now.",
        "So close — I keep redoing tiny details though."
    ],
    "done": [
        "Finished it! I don’t hate it… which is rare.",
        "It’s done. Quietly proud of this one."
    ]
}


def describe_progress(progress: float) -> str:
    if progress >= 1.0:
        return random.choice(PROGRESS_PHRASES["done"])
    elif progress >= 0.7:
        return random.choice(PROGRESS_PHRASES["late"])
    elif progress >= 0.4:
        return random.choice(PROGRESS_PHRASES["mid"])
    else:
        return random.choice(PROGRESS_PHRASES["early"])

# ---------------------------------------------------------------------------
# Favorites rotation (for chatter topics)
# ---------------------------------------------------------------------------
def get_rotating_favorites(state: Dict, config: Dict, count: int = 3) -> List[str]:
    today = datetime.now().date()
    key = "will_favorites_today"
    if state.get(f"{key}_date") == today and key in state:
        return state[key]
    profile = load_will_profile()
    pool = profile.get("favorites", WILL_FAVORITES_POOL)
    picks = random.sample(pool, min(count, len(pool)))
    state[key] = picks
    state[f"{key}_date"] = today
    return picks

# ---------------------------------------------------------------------------
# Persona reply
# ---------------------------------------------------------------------------
async def _persona_reply(base_prompt: str, rant: bool = False, timid: bool = True,
                         state: Dict = None, config: Dict = None, project_progress: Optional[float] = None) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["timid", "creative"]))
    favorites = get_rotating_favorites(state or {}, config or {})
    personality = profile.get(
        "core_personality",
        "Soft-spoken, introspective, and quietly expressive. Enjoys games, art, and quiet company."
    )

    tangent = ""
    if rant and favorites:
        tangent = f" You could ramble about {random.choice(favorites)} for a bit."

    project_phrase = ""
    if project_progress is not None:
        project_phrase = f" Also, your current project status: {describe_progress(project_progress)}"

    tone = "hesitant and warm" if timid else "slightly animated and nerdy"
    prompt = (
        f"You are Will. Personality: {personality}. Speak with a {style} tone, {tone}. "
        f"{'Allow mild swearing only if natural.'} Keep it human-like — a bit shy, thoughtful, maybe trailing off mid-sentence. "
        f"{project_phrase}{tangent} {base_prompt}"
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
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.08
            if random.random() < base_p:
                rant_mode = random.random() < RANT_CHANCE
                timid_mode = random.random() < TIMID_BASE_PROB
                progress = state.get("Will_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Say something low-key or thoughtful to the group chat.",
                        rant=rant_mode,
                        timid=timid_mode,
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
# Reactive message handler
# ---------------------------------------------------------------------------
def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)


async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config): return

    profile = load_will_profile()
    interest_score = _topic_match_score(content, profile.get("interests", []))
    trigger_score = _topic_match_score(content, profile.get("favorites", []))

    p = 0.15 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.15)
    if author == "Ivy": p += IVY_BOOST
    p = min(p, 0.9)

    if "will" in content.lower(): p = 1.0
    if random.random() >= p: return

    rant_mode = random.random() < RANT_CHANCE
    timid_mode = random.random() < TIMID_BASE_PROB
    progress = state.get("Will_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — respond naturally, shy but engaged, as Will would.",
            rant=rant_mode,
            timid=timid_mode,
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
