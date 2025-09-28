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

# Chatter pacing (seconds)
WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

# Probability boosts
INTEREST_HIT_BOOST = 0.35
RANT_CHANCE = 0.10  # baseline

# Favorites
WILL_FAVORITES_POOL = [
    "Legend of Zelda",
    "Final Fantasy",
    "League of Legends",
    "Attack on Titan",
    "Demon Slayer",
    "My Hero Academia",
    "Star Wars",
    "Marvel movies",
    "PC building",
    "retro game consoles",
    "new anime OSTs",
    "VR headsets",
    "streaming marathons",
    "indie games",
    "tech reviews",
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
        "style": ["shy", "casual", "nerdy"],
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

# ---------------- Mood System ----------------
def assign_will_mood(state: Dict):
    """Random daily mood for Will: shy baseline, but can swing."""
    today = datetime.now().date()
    if state.get("will_mood_date") == today:
        return state["will_mood"]

    moods = {
        "withdrawn": 0.25,   # much quieter, hesitant
        "normal": 0.45,      # shy but balanced
        "brave": 0.20,       # more outgoing bursts
        "bad_mood": 0.10,    # grumpy, defensive
    }
    mood = random.choices(list(moods.keys()), weights=moods.values(), k=1)[0]
    state["will_mood"] = mood
    state["will_mood_date"] = today
    return mood


def mood_modifier(base_prob: float, state: Dict) -> float:
    """Adjust Will’s talk probability by mood."""
    mood = assign_will_mood(state)
    if mood == "withdrawn":
        return base_prob * 0.5
    if mood == "normal":
        return base_prob
    if mood == "brave":
        return base_prob * 1.5
    if mood == "bad_mood":
        return base_prob * 0.8 + 0.05  # lower, but still some chance
    return base_prob


# ---------------- Participation Tracker ----------------
def _track_participation(sname, state):
    state.setdefault("last_message_time", {})
    state["last_message_time"][sname] = datetime.now()

def _get_dynamic_weights_for_will(state):
    now = datetime.now()
    last_times = state.get("last_message_time", {})
    base = 1.0

    last_time = last_times.get("Will")
    if last_time:
        silence = (now - last_time).total_seconds() / 3600.0
        base *= (1.0 + min(silence, 6) * 0.25)
    else:
        base *= 2.0

    spoken_today = state.setdefault("spoken_today", {})
    if spoken_today.get("Will", 0) > 4:
        base *= 0.3

    return base


# ---------------- Favorites ----------------
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
async def _post_to_family(message: str, sender: str, sisters, config: Dict, state: Dict):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"{sender} posted: {message}")
                    _track_participation(sender, state)
                    state.setdefault("spoken_today", {})[sender] = state.setdefault("spoken_today", {}).get(sender, 0) + 1
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break


# ---------------- Persona wrapper ----------------
async def _persona_reply(base_prompt: str, rant: bool = False, state: Dict = None, config: Dict = None) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["shy", "casual"]))
    personality = "Shy, nerdy, timid but sometimes excitable. Younger brother energy. Retreats if uncomfortable."

    tangent = ""
    if rant and state is not None and config is not None:
        favorites_today = get_rotating_favorites(state, config)
        if favorites_today and random.random() < 0.6:
            tangent = f" Mention something about {random.choice(favorites_today)}."

    mood = assign_will_mood(state)
    mood_line = f"Today's mood is {mood}. Adjust his tone accordingly."

    extra = (
        f"Make it a shy/animated rant, 2–3 sentences, playful but timid.{tangent}"
        if rant else
        f"Keep it short (1–2 sentences), {style}, hesitant but warm."
    )

    prompt = (
        f"You are Will. Personality: {personality}. {mood_line} "
        f"{base_prompt} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sibling",
        history=[],
    )


# ---------------- Chatter Loop ----------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.12 * _get_dynamic_weights_for_will(state)
            base_p = mood_modifier(base_p, state)
            if random.random() < base_p:
                rant_mode = random.random() < RANT_CHANCE
                try:
                    msg = await _persona_reply("Write a group chat comment.", rant=rant_mode, state=state, config=config)
                    if msg: await _post_to_family(msg, "Will", sisters, config, state)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))


# ---------------- Reactive Handler ----------------
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config): return

    profile = load_will_profile()
    interest_score = _topic_match_score(content, profile.get("interests", []))
    trigger_score = _topic_match_score(content, profile.get("triggers", []))

    mentioned = "will" in content.lower()

    p = 0.1 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.20)
    if author.lower() == "ivy":
        p += 0.25
    if mentioned:
        p = 1.0

    p = mood_modifier(p, state)

    if random.random() > min(p, 0.9): return

    rant_mode = random.random() < RANT_CHANCE
    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\". Reply shyly, like Will would.",
            rant=rant_mode, state=state, config=config
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config, state)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")


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


# ---------------- Startup ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    assign_will_mood(state)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))


# ---------------- Topic match helper ----------------
def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)
