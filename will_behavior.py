# will_behavior.py
import os
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event
from relationships import adjust_relationship

# Will's dynamic profile loader
DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]

WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

# Chatter pacing
WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

# Probabilities
INTEREST_HIT_BOOST = 0.3
IVY_BOOST = 0.25
DRAMATIC_SHIFT_BASE = 0.04
RANT_CHANCE = 0.07

# Favorites
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
        "dislikes": ["conflict", "arguments", "drama"],
        "style": ["timid", "casual", "hesitant", "sometimes playful"],
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
def get_rotating_favorites(state: Dict, config: Dict, count: int = 2) -> List[str]:
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
    wake_rng = scfg.get("wake", [10, 12])
    sleep_rng = scfg.get("sleep", [0, 2])

    def _pick(hr):
        lo, hi = int(hr[0]), int(hr[1])
        return random.randint(lo, hi) if hi >= lo else lo

    schedule = {"wake": _pick(wake_rng), "sleep": _pick(sleep_rng)}
    state[key] = schedule
    state[f"{key}_date"] = today
    return schedule

def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_hour = datetime.now().hour
    wake, sleep = sc["wake"], sc["sleep"]
    if wake == sleep: return True
    if wake < sleep: return wake <= now_hour < sleep
    return now_hour >= wake or now_hour < sleep

# ---------------- Persona wrapper ----------------
async def _persona_reply(base_prompt: str, rant: bool = False, timid: bool = True,
                         state: Dict = None, config: Dict = None) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["timid", "casual"]))
    personality = "Shy, nerdy, hesitant, often second-guesses himself but warms up when comfortable."

    tangent = ""
    if rant and state is not None and config is not None:
        favorites_today = get_rotating_favorites(state, config)
        if favorites_today and random.random() < 0.6:
            tangent = f" Maybe mention {random.choice(favorites_today)}."

    tone = "hesitant, quiet, slightly self-conscious" if timid else "momentarily confident but quick to retreat"
    extra = (
        f"Make it ranty/animated in 2–3 sentences, but still tinged with nervousness.{tangent}"
        if rant else
        f"Keep it brief (1–2 sentences), {style}, {tone}."
    )

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"{base_prompt} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------- Rant Chance Helper ----------------
def calculate_rant_chance(base: float, interest_score: float = 0, trigger_score: float = 0) -> float:
    now_hour = datetime.now().hour
    rant_chance = base
    if 20 <= now_hour or now_hour <= 1: rant_chance *= 1.5
    if interest_score > 0: rant_chance += 0.1
    if trigger_score > 0: rant_chance += 0.15
    return min(rant_chance, 1.0)

# ---------------- Chatter Loop ----------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.1  # shy baseline
            if random.random() < 0.05: base_p += 0.08
            if random.random() < base_p:
                rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE)
                timid_mode = random.random() > 0.25  # 75% timid
                try:
                    msg = await _persona_reply(
                        "Say something small to the group.",
                        rant=rant_mode, timid=timid_mode,
                        state=state, config=config
                    )
                    if msg:
                        await _post_to_family(msg, "Will", sisters, config)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------------- Reactive Handler ----------------
async def will_handle_message(state: Dict, config: Dict, sisters,
                              author: str, content: str, channel_id: int):
    if not is_will_online(state, config): return

    profile = load_will_profile()
    interest_score = _topic_match_score(content, profile.get("interests", []))
    trigger_score = _topic_match_score(content, profile.get("triggers", []))

    p = 0.08 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.15)
    if author == "Ivy": p += IVY_BOOST
    if "will" in content.lower(): p = 1.0
    p = min(p, 0.9)

    if random.random() >= p: return

    rant_chance = calculate_rant_chance(RANT_CHANCE, interest_score, trigger_score)
    rant_mode = random.random() < rant_chance
    timid_mode = random.random() > 0.25

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\". Reply shyly, in your own style.",
            rant=rant_mode, timid=timid_mode,
            state=state, config=config
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config)
            # Relationship nudges
            if author == "Ivy":
                adjust_relationship(state, "Will", "Ivy", "affection", +0.07)
            else:
                adjust_relationship(state, "Will", author, "affection", +0.04)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

# ---------------- Startup Helper ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))

# ---------------- Topic match helper ----------------
def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)
