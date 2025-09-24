import os
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]

WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

INTEREST_HIT_BOOST = 0.35
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.10

WILL_FAVORITES_POOL = [
    "Legend of Zelda", "Final Fantasy", "League of Legends",
    "Attack on Titan", "Demon Slayer", "My Hero Academia",
    "Star Wars", "Marvel movies", "PC building",
    "retro game consoles", "new anime OSTs", "VR headsets",
    "streaming marathons", "indie games", "tech reviews",
    "cosplay communities",
]

# ---------------- Profile ----------------
def _read_file_first(path_list: List[str]) -> Optional[str]:
    for p in path_list:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                continue
    return None

def load_will_profile() -> Dict:
    text = _read_file_first(DEFAULT_PROFILE_PATHS) or ""
    profile = {
        "interests": ["tech", "games", "anime", "music"],
        "dislikes": ["drama"],
        "style": ["casual", "snarky"],
        "triggers": ["hype", "memes", "nostalgia"],
        "favorites": WILL_FAVORITES_POOL,
    }
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

# ---------------- Favorites rotation ----------------
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

# ---------------- Messaging ----------------
async def _post_to_family(message: str, sender: str, sisters, config: Dict):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break

# ---------------- Schedule ----------------
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "will_schedule"
    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]
    scfg = config.get("schedules", {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    wake_rng, sleep_rng = scfg.get("wake", [10, 12]), scfg.get("sleep", [0, 2])
    def _pick(hr): return random.randint(int(hr[0]), int(hr[1]))
    schedule = {"wake": _pick(wake_rng), "sleep": _pick(sleep_rng)}
    state[key], state[f"{key}_date"] = schedule, today
    return schedule

def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_hour, wake, sleep = datetime.now().hour, sc["wake"], sc["sleep"]
    if wake == sleep: return True
    if wake < sleep: return wake <= now_hour < sleep
    return now_hour >= wake or now_hour < sleep

# ---------------- Persona wrapper ----------------
async def _persona_reply(base_prompt: str, rant: bool = False, state: Dict = None, config: Dict = None) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual"]))
    favorites_today = get_rotating_favorites(state, config)
    tangent = ""
    if rant and favorites_today and random.random() < 0.7:
        tangent = f" Mention something about {random.choice(favorites_today)}."
    extra = "Ranty/animated, 2–3 sentences." + tangent if rant else f"Short (1–2 sentences), {style}, brotherly."
    prompt = f"You are Will. Personality: casual, nerdy, dramatic. {base_prompt} {extra}"
    return await generate_llm_reply("Will", prompt, None, "sister", [])

# ---------------- Rant chance ----------------
def calculate_rant_chance(base: float, interest_score: float = 0, trigger_score: float = 0) -> float:
    now_hour, rant_chance = datetime.now().hour, base
    if 20 <= now_hour or now_hour <= 1: rant_chance *= 2
    if interest_score > 0: rant_chance += 0.15
    if trigger_score > 0: rant_chance += 0.20
    return min(rant_chance, 1.0)

# ---------------- Chatter ----------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True
    while True:
        if is_will_online(state, config) and random.random() < 0.2:
            rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE)
            try:
                msg = await _persona_reply("Make a group chat comment.", rant=rant_mode, state=state, config=config)
                if msg: await _post_to_family(msg, "Will", sisters, config)
            except Exception as e: log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------------- Cooldowns ----------------
def _check_cooldown(state: Dict, key: str, seconds: int) -> bool:
    """Return True if allowed, False if still cooling down."""
    now = datetime.now()
    last = state.get(key)
    if last and (now - last).total_seconds() < seconds:
        return False
    state[key] = now
    return True

# ---------------- Reactive to user/sisters ----------------
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config): return
    if not _check_cooldown(state, "will_global_cooldown", 45):  # 45s global cooldown
        return

    profile = load_will_profile()
    interest_score = sum(1 for i in profile["interests"] if i.lower() in content.lower())
    trigger_score = sum(1 for t in profile["triggers"] if t.lower() in content.lower())
    p = min(0.15 + interest_score*INTEREST_HIT_BOOST + trigger_score*0.2, 0.85)
    if random.random() >= p: return
    rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE, interest_score, trigger_score)
    reply = await _persona_reply(f"{author} said: \"{content}\". Reply like Will would.", rant=rant_mode, state=state, config=config)
    if reply: await _post_to_family(reply, "Will", sisters, config)

# ---------------- Sister-specific replies ----------------
async def will_reply_to_sister(state: Dict, config: Dict, sisters, author: str, content: str):
    if not is_will_online(state, config): return
    if not _check_cooldown(state, f"will_cd_{author}", 60):  # 1-min per-sister cooldown
        return

    favorites_today = get_rotating_favorites(state, config)
    if author == "Aria":
        base_prompt = f"Aria said: \"{content}\". Softer reply, slightly appreciative, still brotherly."
    elif author == "Selene":
        base_prompt = f"Selene said: \"{content}\". Half-teasing but let her motherly tone land. Maybe drop in {random.choice(favorites_today)}."
    elif author == "Cassandra":
        base_prompt = f"Cassandra said: \"{content}\". Bratty or defensive comeback, sarcastic allowed."
    elif author == "Ivy":
        base_prompt = f"Ivy said: \"{content}\". Banter back, snarky or meme-ish. Maybe reference {random.choice(favorites_today)}."
    else:
        base_prompt = f"{author} said: \"{content}\". Casual nerdy reply."
    reply = await _persona_reply(base_prompt, rant=False, state=state, config=config)
    if reply: await _post_to_family(reply, "Will", sisters, config)

# ---------------- Startup ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
