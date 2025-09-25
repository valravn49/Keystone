import os
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# Will's dynamic profile loader
DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]

WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

# Chatter pacing
WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

# Probability boosts
INTEREST_HIT_BOOST = 0.35
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.10

WILL_FAVORITES_POOL = [
    "Legend of Zelda", "Final Fantasy", "League of Legends",
    "Attack on Titan", "Demon Slayer", "My Hero Academia",
    "Star Wars", "Marvel movies", "PC building", "retro game consoles",
    "new anime OSTs", "VR headsets", "streaming marathons",
    "indie games", "tech reviews", "cosplay communities",
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
        if low.startswith("favorites:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["favorites"] = vals
    return profile

def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    return sum(1.0 for kw in keywords if kw.lower() in content.lower())

# ---------------- Messaging ----------------
async def _post_to_family(message: str, sisters, config: Dict):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == "Will":
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"Will posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break

# ---------------- Schedule ----------------
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    if state.get("will_schedule_date") == today and state.get("will_schedule"):
        return state["will_schedule"]

    scfg = config.get("schedules", {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    wake_rng, sleep_rng = scfg["wake"], scfg["sleep"]

    def _pick(rng): return random.randint(rng[0], rng[1])
    schedule = {"wake": _pick(wake_rng), "sleep": _pick(sleep_rng)}

    state["will_schedule"] = schedule
    state["will_schedule_date"] = today
    return schedule

def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    hour = datetime.now().hour
    wake, sleep = sc["wake"], sc["sleep"]
    if wake == sleep: return True
    if wake < sleep: return wake <= hour < sleep
    return hour >= wake or hour < sleep

# ---------------- Persona ----------------
async def _persona_reply(base_prompt: str, rant=False, state=None, config=None) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual"]))
    personality = "Casual, nerdy, sometimes dramatic. Younger brother energy."

    tangent = ""
    if rant and state and config:
        favs = profile.get("favorites", WILL_FAVORITES_POOL)
        if favs and random.random() < 0.7:
            tangent = f" Throw in something about {random.choice(favs)}."

    extra = (
        f"Make it ranty/animated, 2–3 sentences, playful but dramatic.{tangent}"
        if rant else
        f"Keep it short (1–2 sentences), {style}, brotherly and casual."
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=f"You are Will. Personality: {personality}. {base_prompt} {extra}",
        theme=None,
        role="sister",
        history=[],
    )

# ---------------- Rant Chance ----------------
def calculate_rant_chance(base: float, interest_score=0, trigger_score=0) -> float:
    hour = datetime.now().hour
    rant_chance = base * (2 if hour >= 20 or hour <= 1 else 1)
    rant_chance += 0.15 * interest_score + 0.20 * trigger_score
    return min(rant_chance, 1.0)

# ---------------- Chatter ----------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True
    while True:
        if is_will_online(state, config) and random.random() < 0.2:
            rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE)
            try:
                msg = await _persona_reply("Say something to the group chat.", rant=rant_mode, state=state, config=config)
                if msg: await _post_to_family(msg, sisters, config)
            except Exception as e:
                log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------------- Reactive ----------------
async def will_handle_message(state, config, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config): return
    profile = load_will_profile()
    interest, trigger = _topic_match_score(content, profile["interests"]), _topic_match_score(content, profile["triggers"])
    p = min(0.15 + interest * INTEREST_HIT_BOOST + trigger * 0.20, 0.85)
    if random.random() >= p: return

    rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE, interest, trigger)
    prompt = f"{author} said: \"{content}\". Reply like Will would."
    try:
        reply = await _persona_reply(prompt, rant=rant_mode, state=state, config=config)
        if reply: await _post_to_family(reply, sisters, config)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

# ---------------- Participation ----------------
async def will_maybe_participate(state, config, sisters, context: str):
    """Let Will join in after sisters interact with each other."""
    if not is_will_online(state, config): return
    if random.random() > 0.25: return  # 25% base chance to jump in

    rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE)
    try:
        reply = await _persona_reply(
            f"Chime in casually after the sisters: {context}",
            rant=rant_mode, state=state, config=config
        )
        if reply: await _post_to_family(reply, sisters, config)
    except Exception as e:
        log_event(f"[ERROR] Will participate: {e}")

# ---------------- Startup ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
