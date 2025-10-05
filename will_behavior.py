import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# ---------------------------------------------------------------------------
# Profile & memory (lightweight, optional JSONs)
# ---------------------------------------------------------------------------

DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",       # legacy text (optional)
    "/mnt/data/Will_Profile.txt",  # legacy text (optional)
]

WILL_PERSONALITY_JSON = "/mnt/data/Will_Personality.json"  # optional modern JSON
WILL_MEMORY_JSON = "/mnt/data/Will_Memory.json"            # optional modern JSON

WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

# Chatter pacing (seconds) — shy cadence
WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

# Probability shaping
INTEREST_HIT_BOOST = 0.35
IVY_BOOST = 0.25
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.10

# Master favorites (fallback)
WILL_FAVORITES_POOL = [
    "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
    "Stardew Valley", "Hollow Knight", "Elden Ring",
    "VR headsets", "retro game consoles", "PC building",
    "indie game dev videos", "tech teardown channels",
]

# ---------------------------------------------------------------------------

def _read_file_first(path_list: List[str]) -> Optional[str]:
    for p in path_list:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                continue
    return None

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Will JSON read failed {path}: {e}")
    return default

def load_will_profile() -> Dict:
    # Prefer JSON if available, else text profile for a few fields, else fallback defaults
    j = _load_json(WILL_PERSONALITY_JSON, {})
    profile = {
        "interests": j.get("interests", ["tech", "games", "anime", "music"]),
        "dislikes": j.get("dislikes", ["drama"]),
        "style": j.get("style", ["casual", "timid", "sometimes playful"]),
        "triggers": j.get("triggers", ["hype", "memes", "nostalgia"]),
        "favorites": j.get("favorites", WILL_FAVORITES_POOL),
    }

    # Legacy TXT extraction if present (best-effort)
    text = _read_file_first(DEFAULT_PROFILE_PATHS) or ""
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("interests:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["interests"] = vals
        elif low.startswith("dislikes:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["dislikes"] = vals
        elif low.startswith("style:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["style"] = vals
        elif low.startswith("triggers:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["triggers"] = vals
        elif low.startswith("favorites:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["favorites"] = vals

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
# Favorites rotation (for small rants/enthusiasm)
# ---------------------------------------------------------------------------

def get_rotating_favorites(state: Dict, config: Dict, count: int = 3) -> List[str]:
    today = datetime.now().date()
    key = "will_favorites_today"
    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]

    profile = load_will_profile()
    pool = profile.get("favorites", WILL_FAVORITES_POOL)
    picks = random.sample(pool, min(count, len(pool)))
    state[key] = picks
    state[f"{key}_date"] = today
    return picks

# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

async def _post_to_family(message: str, sender: str, sisters, config: Dict):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break

# ---------------------------------------------------------------------------
# Schedule (uses config["schedules"]["Will"] with [lo,hi] hour ranges)
# ---------------------------------------------------------------------------

def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "will_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and state.get(key):
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        return random.randint(lo, hi) if hi >= lo else lo
    schedule = {"wake": pick(scfg.get("wake", [10, 12])), "sleep": pick(scfg.get("sleep", [0, 2]))}
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
    now_h = datetime.now().hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------------------------------------------------------------------------
# Persona wrapper
# ---------------------------------------------------------------------------

PROGRESS_PHRASES = {
    "early": [
        "I just… started, not much to show yet.",
        "Barely touched it — first step only.",
    ],
    "mid": [
        "It’s coming along slowly — I’ve got a chunk done.",
        "Kinda in the middle, but I keep second-guessing stuff.",
    ],
    "late": [
        "Almost finished — just ironing out the last little bits.",
        "Close to done, I’m just… stalling on the ending.",
    ],
    "done": [
        "I actually finished it — quietly proud, I guess.",
        "Done at last. More relief than excitement.",
    ],
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

async def _persona_reply(
    base_prompt: str,
    rant: bool = False,
    timid: bool = True,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual", "timid"]))
    personality = "Shy, nerdy, hesitant; sometimes playful or briefly dramatic."

    tangent = ""
    if rant and state is not None and config is not None:
        favorites_today = get_rotating_favorites(state, config)
        if favorites_today and random.random() < 0.6:
            tangent = f" Maybe mention {random.choice(favorites_today)}."

    project_phrase = ""
    if project_progress is not None:
        project_phrase = f" Also, about your current project: {describe_progress(project_progress)}"

    tone = "hesitant and soft-spoken" if timid else "more outgoing and animated"
    extra = (
        f"Make it a small, animated rant (2–3 sentences) but keep the shy undertone.{tangent}{project_phrase}"
        if rant else
        f"Keep it brief (1–2 sentences), {style}, brotherly but {tone}.{project_phrase}"
    )

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"Swearing is allowed only if it feels natural and mild. "
        f"{base_prompt} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------------------------------------------------------------------
# Rant chance helper
# ---------------------------------------------------------------------------

def calculate_rant_chance(base: float, interest_score: float = 0, trigger_score: float = 0) -> float:
    now_hour = datetime.now().hour
    rant_chance = base
    if 20 <= now_hour or now_hour <= 1:
        rant_chance *= 2
    if interest_score > 0:
        rant_chance += 0.15
    if trigger_score > 0:
        rant_chance += 0.20
    return min(rant_chance, 1.0)

# ---------------------------------------------------------------------------
# Background chatter
# ---------------------------------------------------------------------------

async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"):
        return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.10  # shy base
            if random.random() < 0.05:
                base_p += 0.10  # occasional burst window
            if random.random() < base_p:
                rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE)
                timid_mode = random.random() > 0.25  # 75% timid replies
                progress = state.get("Will_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Drop a short, natural group-chat comment.",
                        rant=rant_mode,
                        timid=timid_mode,
                        state=state,
                        config=config,
                        project_progress=progress,
                    )
                    if msg:
                        await _post_to_family(msg, "Will", sisters, config)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------------------------------------------------------------------------
# Reactive handler
# ---------------------------------------------------------------------------

def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)

async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config):
        return

    profile = load_will_profile()
    interest_score = _topic_match_score(content, profile.get("interests", []))
    trigger_score = _topic_match_score(content, profile.get("triggers", []))

    p = 0.12 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.20)
    if author == "Ivy":
        p += IVY_BOOST  # Ivy increases Will’s chance to talk
    p = min(p, 0.9)

    # Always respond if directly mentioned
    if "will" in content.lower():
        p = 1.0

    if random.random() >= p:
        return

    rant_chance = calculate_rant_chance(RANT_CHANCE, interest_score, trigger_score)
    rant_mode = random.random() < rant_chance
    timid_mode = random.random() > 0.25
    progress = state.get("Will_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply like Will would.',
            rant=rant_mode,
            timid=timid_mode,
            state=state,
            config=config,
            project_progress=progress,
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
