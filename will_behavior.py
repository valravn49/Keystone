# will_behavior.py
import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# =============================================================================
# Personality & memory file locations
# =============================================================================
WILL_PERSONALITY_JSON = "/mnt/data/Will_Personality.json"
WILL_MEMORY_JSON = "/mnt/data/Will_Memory.json"
WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

# Fallback legacy text sources (optional)
LEGACY_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]

# =============================================================================
# Behavior timing & mood constants
# =============================================================================
WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 95 * 60

INTEREST_HIT_BOOST = 0.35
IVY_BOOST = 0.25
RANT_CHANCE = 0.10

# Realistic favorite pool
WILL_FAVORITES_POOL = [
    "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
    "Stardew Valley", "Hollow Knight", "Elden Ring",
    "PC building", "retro game consoles", "VR headsets",
    "indie game dev videos", "tech teardown channels",
]

REAL_MEDIA = [
    "Attack on Titan", "Demon Slayer", "My Hero Academia", "The Mandalorian",
    "Arcane", "The Last of Us", "Stranger Things", "Stardew Valley",
    "Hollow Knight", "Final Fantasy XIV", "Zelda"
]

# =============================================================================
# Helpers: file I/O
# =============================================================================
def _read_file_first(paths: List[str]) -> Optional[str]:
    for p in paths:
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

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Will JSON write failed {path}: {e}")

# =============================================================================
# Profile & memory
# =============================================================================
def load_will_profile() -> Dict:
    j = _load_json(WILL_PERSONALITY_JSON, {})
    profile = {
        "interests": j.get("interests", ["tech", "games", "anime", "music"]),
        "dislikes": j.get("dislikes", ["drama"]),
        "style": j.get("style", ["casual", "timid", "sometimes playful"]),
        "triggers": j.get("triggers", ["hype", "memes", "nostalgia"]),
        "favorites": j.get("favorites", WILL_FAVORITES_POOL),
    }
    # try legacy text file extraction
    text = _read_file_first(LEGACY_PATHS) or ""
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("interests:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals:
                profile["interests"] = vals
        elif low.startswith("dislikes:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals:
                profile["dislikes"] = vals
        elif low.startswith("favorites:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals:
                profile["favorites"] = vals
    return profile

def load_will_memory() -> Dict:
    mem = _load_json(WILL_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_will_memory(mem: Dict):
    _save_json(WILL_MEMORY_JSON, mem)

# =============================================================================
# Internal helpers
# =============================================================================
def get_rotating_favorites(state: Dict, config: Dict, count: int = 3) -> List[str]:
    today = datetime.now().date()
    key = "will_favorites_today"
    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]
    pool = load_will_profile().get("favorites", WILL_FAVORITES_POOL)
    picks = random.sample(pool, min(count, len(pool)))
    state[key] = picks
    state[f"{key}_date"] = today
    return picks

def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    t = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in t)

def _media_hits(content: str) -> list:
    t = content.lower()
    return [m for m in REAL_MEDIA if m.lower() in t]

# =============================================================================
# Persona: progress phrasing and speech construction
# =============================================================================
PROGRESS_PHRASES = {
    "early": [
        "I just… started. It’s kind of messy still.",
        "Barely touched it — more ideas than progress."
    ],
    "mid": [
        "It’s coming along, but slower than I thought.",
        "I’m halfway, I think. Still tweaking stuff."
    ],
    "late": [
        "Almost done, just fixing little details.",
        "It’s close. I just need to stop nitpicking."
    ],
    "done": [
        "I actually finished it — weirdly proud of myself.",
        "It’s done, finally. Relief feels better than excitement."
    ]
}

def describe_progress(p: float) -> str:
    if p >= 1.0:
        return random.choice(PROGRESS_PHRASES["done"])
    if p >= 0.7:
        return random.choice(PROGRESS_PHRASES["late"])
    if p >= 0.4:
        return random.choice(PROGRESS_PHRASES["mid"])
    return random.choice(PROGRESS_PHRASES["early"])

# =============================================================================
# Persona reply generation
# =============================================================================
async def _persona_reply(
    base_prompt: str,
    timid: bool = True,
    rant: bool = False,
    project_progress: Optional[float] = None,
    inject_media: Optional[str] = None
) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual", "timid"]))
    personality = (
        "Shy, nerdy, hesitant, but kind and attentive. "
        "He’s the youngest brother type — easily flustered, observant, sometimes funny on accident."
    )

    project_phrase = ""
    if project_progress is not None:
        project_phrase = f" Also mention your project: {describe_progress(project_progress)}."

    media_clause = f" Maybe reference {inject_media} if it feels natural." if inject_media else ""

    tone = "soft, hesitant" if timid else "a little bolder, like he’s trying to keep up with the others"
    rant_clause = "Make it a short excited tangent (2–3 sentences) but still shy underneath." if rant else ""

    prompt = (
        f"You are Will. Personality: {personality} "
        f"Style: {style}. {tone}. {rant_clause}{project_phrase}{media_clause} "
        f"{base_prompt}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[]
    )

# =============================================================================
# Schedule
# =============================================================================
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key, kd = "will_schedule", "will_schedule_date"
    if state.get(kd) == today and key in state:
        return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    def pick(span): lo, hi = int(span[0]), int(span[1]); return random.randint(lo, hi)
    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key], state[kd] = schedule, today
    return schedule

def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    h = datetime.now().hour
    w, s = sc["wake"], sc["sleep"]
    if w == s: return True
    return w <= h < s if w < s else h >= w or h < s

# =============================================================================
# Posting
# =============================================================================
async def _post_to_family(msg: str, sisters, config: Dict):
    for b in sisters:
        if b.sister_info["name"] == "Will" and b.is_ready():
            try:
                ch = b.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(msg)
                    log_event(f"Will posted: {msg}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break

# =============================================================================
# Mood shaping
# =============================================================================
def calculate_rant_chance(base: float, interest: float = 0, trigger: float = 0) -> float:
    now_h = datetime.now().hour
    r = base
    if 20 <= now_h or now_h <= 1:
        r *= 2
    if interest > 0:
        r += 0.15
    if trigger > 0:
        r += 0.2
    return min(r, 1.0)

# =============================================================================
# Background chatter
# =============================================================================
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"):
        return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            if random.random() < 0.1:
                rant = random.random() < calculate_rant_chance(RANT_CHANCE)
                timid = random.random() > 0.25
                progress = state.get("Will_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Write a short, natural group chat message. Mention or respond to what’s going on today if it feels right.",
                        timid=timid,
                        rant=rant,
                        project_progress=progress
                    )
                    if msg:
                        await _post_to_family(msg, sisters, config)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# =============================================================================
# Reactive behavior (responds to siblings)
# =============================================================================
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config):
        return

    profile = load_will_profile()
    interest = _topic_match_score(content, profile.get("interests", []))
    trigger = _topic_match_score(content, profile.get("triggers", []))
    media_refs = _media_hits(content)

    p = 0.15 + (interest * INTEREST_HIT_BOOST) + (trigger * 0.20)
    if author == "Ivy":
        p += IVY_BOOST
    if "will" in content.lower():
        p = 1.0
    if random.random() >= min(0.9, p):
        return

    rant = random.random() < calculate_rant_chance(RANT_CHANCE, interest, trigger)
    timid = random.random() > 0.25
    progress = state.get("Will_project_progress", random.random())
    inject = random.choice(media_refs) if media_refs and random.random() < 0.6 else None

    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply like Will would — shy but engaged. Keep it brief and real.',
            timid=timid,
            rant=rant,
            project_progress=progress,
            inject_media=inject
        )
        if reply:
            await _post_to_family(reply, sisters, config)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

# =============================================================================
# Startup
# =============================================================================
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
