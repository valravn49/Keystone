import os
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# Will's profile paths
DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]
WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

# Chatter pacing
WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

# Probability tuning
INTEREST_HIT_BOOST = 0.35
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.10

# Favorites pool
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
        "style": ["casual", "shy"],
        "triggers": ["hype", "memes", "nostalgia"],
        "favorites": WILL_FAVORITES_POOL,
    }
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("interests:"):
            profile["interests"] = [x.strip() for x in line.split(":", 1)[1].split(",")]
        elif low.startswith("dislikes:"):
            profile["dislikes"] = [x.strip() for x in line.split(":", 1)[1].split(",")]
        elif low.startswith("style:"):
            profile["style"] = [x.strip() for x in line.split(":", 1)[1].split(",")]
        elif low.startswith("triggers:"):
            profile["triggers"] = [x.strip() for x in line.split(":", 1)[1].split(",")]
        elif low.startswith("favorites:"):
            profile["favorites"] = [x.strip() for x in line.split(":", 1)[1].split(",")]
    return profile


# ---------------- Favorites rotation ----------------
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
    return wake <= now_hour < sleep if wake < sleep else now_hour >= wake or now_hour < sleep


# ---------------- Persona reply ----------------
async def _persona_reply(base_prompt: str, rant: bool, state: Dict, config: Dict) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual"]))
    personality = "Shy, nerdy younger brother. Often hesitant, sometimes dramatic when excited."

    tangent = ""
    if rant:
        favs = get_rotating_favorites(state, config)
        if favs and random.random() < 0.7:
            tangent = f" Mention something about {random.choice(favs)}."

    extra = "Make it shy but playful, 2–3 sentences." + tangent if rant else f"Keep it short (1–2 sentences), {style}, timid and hesitant."

    return await generate_llm_reply(
        sister="Will",
        user_message=f"You are Will. Personality: {personality}. {base_prompt} {extra}",
        theme=None,
        role="sister",
        history=[],
    )


# ---------------- Rant chance ----------------
def calculate_rant_chance(base: float, interest_score: float = 0, trigger_score: float = 0) -> float:
    rant_chance = base
    now_hour = datetime.now().hour
    if 20 <= now_hour or now_hour <= 1: rant_chance *= 2
    if interest_score > 0: rant_chance += 0.15
    if trigger_score > 0: rant_chance += 0.20
    return min(rant_chance, 1.0)


# ---------------- Chatter loop ----------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            if random.random() < 0.2:  # base chance
                rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE)
                try:
                    msg = await _persona_reply("Write a group chat comment.", rant_mode, state, config)
                    if msg: await _post_to_family(msg, "Will", sisters, config)
                except Exception as e: log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))


# ---------------- Reactive handler ----------------
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config): return

    profile = load_will_profile()
    interest_score = sum(1 for kw in profile["interests"] if kw.lower() in content.lower())
    trigger_score = sum(1 for kw in profile["triggers"] if kw.lower() in content.lower())

    p = 0.15 + interest_score * INTEREST_HIT_BOOST + trigger_score * 0.2
    if author.lower().startswith("ivy"): p += 0.25
    if "will" in content.lower(): p = 1.0
    p = min(p, 0.9)

    if random.random() >= p: return

    rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE, interest_score, trigger_score)

    # Context
    context_snippets = []
    if "history" in state:
        recent_msgs = list(state["history"].values())[-5:]
        context_snippets = [f"{h['author']}: {h['content']}" for h in recent_msgs]
    convo_context = "\n".join(context_snippets) if context_snippets else "No prior context."

    prompt = (
        f"{author} said: \"{content}\". Recent chat:\n{convo_context}\n"
        f"Reply like Will would — shy, nerdy, sometimes dramatic. "
        f"{'Make it a rant if excited.' if rant_mode else 'Keep it timid and short.'}"
    )

    try:
        reply = await _persona_reply(prompt, rant_mode, state, config)
        if reply: await _post_to_family(reply, "Will", sisters, config)
    except Exception as e: log_event(f"[ERROR] Will reactive: {e}")


# ---------------- Startup helper ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
