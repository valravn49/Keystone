import os
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# Will's dynamic profile loader
DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]

WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

# Chatter pacing (seconds)
WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

# Probability boosts
INTEREST_HIT_BOOST = 0.25
IVY_BOOST = 0.25
MENTION_BOOST = 0.60
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.08  # baseline rant chance

# Ghosting
GHOST_CHANCE = 0.25
GHOST_CHANCE_AFTER_RANT = 0.55
GHOST_MIN = 10 * 60   # 10 min
GHOST_MAX = 40 * 60   # 40 min

# Master favorites pool
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


# ---------------- Helpers ----------------
def convert_hour(hour: int) -> int:
    """Shift hour: if <10 → add 14, else subtract 10."""
    return (hour + 14) % 24 if hour < 10 else (hour - 10) % 24


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
        "style": ["casual", "timid", "sometimes snarky"],
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
    wake_rng = scfg.get("wake", [10, 12])
    sleep_rng = scfg.get("sleep", [0, 2])

    def _pick(hr):
        lo, hi = int(hr[0]), int(hr[1])
        return random.randint(lo, hi) if hi >= lo else lo

    wake = convert_hour(_pick(wake_rng))
    sleep = convert_hour(_pick(sleep_rng))

    schedule = {"wake": wake, "sleep": sleep}
    state[key] = schedule
    state[f"{key}_date"] = today
    return schedule


def is_will_online(state: Dict, config: Dict) -> bool:
    if state.get("will_ghost_until"):
        if datetime.now() < state["will_ghost_until"]:
            return False
        else:
            state["will_ghost_until"] = None
            state["will_needs_apology"] = True  # mark that he should apologize when back

    sc = assign_will_schedule(state, config)
    now_hour = datetime.now().hour
    wake, sleep = sc["wake"], sc["sleep"]
    if wake == sleep: return True
    if wake < sleep: return wake <= now_hour < sleep
    return now_hour >= wake or now_hour < sleep


def maybe_trigger_ghost(state: Dict, after_rant: bool = False):
    chance = GHOST_CHANCE_AFTER_RANT if after_rant else GHOST_CHANCE
    if random.random() < chance:
        duration = random.randint(GHOST_MIN, GHOST_MAX)
        state["will_ghost_until"] = datetime.now() + timedelta(seconds=duration)
        log_event(f"[WILL] Ghosting triggered for {duration//60} min "
                  f"{'(after rant)' if after_rant else ''}.")


# ---------------- Persona wrapper ----------------
async def _persona_reply(base_prompt: str, rant: bool = False, shy: bool = False,
                         state: Dict = None, config: Dict = None, force_apology: bool = False) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual", "timid"]))
    personality = "Shy, nerdy, sometimes dramatic. Younger brother energy."

    if force_apology:
        base_prompt = (
            "You were quiet/absent for a while. Write a hesitant, apologetic 1–2 sentence "
            "message about being away, like you felt awkward or embarrassed. "
            "Make it timid but sincere."
        )

    tangent = ""
    if rant and state is not None and config is not None:
        favorites_today = get_rotating_favorites(state, config)
        if favorites_today and random.random() < 0.6:
            tangent = f" Maybe mention {random.choice(favorites_today)}."

    tone = "Keep it hesitant, shorter, and softer." if shy else f"Keep it {style}, brotherly and casual."

    extra = (
        f"Make it ranty/animated, 2–3 sentences, playful but dramatic.{tangent}"
        if rant and not force_apology else tone
    )

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"Swearing is allowed if natural. "
        f"{base_prompt} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )


# ---------------- Chatter Loop ----------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.15
            if random.random() < 0.1: base_p += 0.1
            if random.random() < base_p:
                rant_mode = random.random() < RANT_CHANCE
                shy_mode = random.random() < 0.4
                try:
                    msg = await _persona_reply(
                        "Write a group chat comment.",
                        rant=rant_mode,
                        shy=shy_mode,
                        state=state,
                        config=config,
                        force_apology=state.pop("will_needs_apology", False)
                    )
                    if msg:
                        await _post_to_family(msg, "Will", sisters, config)
                        maybe_trigger_ghost(state, after_rant=rant_mode)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))


# ---------------- Reactive Handler ----------------
async def will_handle_message(state: Dict, config: Dict, sisters, author: str,
                              content: str, channel_id: int):
    if not is_will_online(state, config): return

    profile = load_will_profile()
    interest_score = sum(1.0 for kw in profile.get("interests", []) if kw.lower() in content.lower())
    trigger_score = sum(1.0 for kw in profile.get("triggers", []) if kw.lower() in content.lower())

    p = 0.12 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.20)
    if author.lower().startswith("ivy"):
        p += IVY_BOOST
    if "will" in content.lower() or "brother" in content.lower():
        p += MENTION_BOOST

    p = min(p, 0.9)
    if random.random() >= p: return

    rant_mode = random.random() < RANT_CHANCE
    shy_mode = random.random() < 0.6

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\". Reply like Will would.",
            rant=rant_mode,
            shy=shy_mode,
            state=state,
            config=config,
            force_apology=state.pop("will_needs_apology", False)
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config)
            maybe_trigger_ghost(state, after_rant=rant_mode)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")


# ---------------- Startup Helper ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
