# will_behavior.py
import os
import json
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

# Chatter pacing (seconds)
WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

# Probability boosts
INTEREST_HIT_BOOST = 0.35
DRAMATIC_SHIFT_BASE = 0.05


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
    """
    Parse Will's profile from a simple TXT format. Expected loose format like:
      Interests: games, tech, anime
      Dislikes: drama, arguments
      Style: casual, teasing, nerdy
      Triggers: hype, memes, nostalgia
    """
    text = _read_file_first(DEFAULT_PROFILE_PATHS) or ""
    profile = {
        "interests": ["tech", "games", "anime", "music"],
        "dislikes": ["drama"],
        "style": ["casual", "snarky"],
        "triggers": ["hype", "memes", "nostalgia"],
    }
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
        elif low.startswith("style:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals:
                profile["style"] = vals
        elif low.startswith("triggers:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals:
                profile["triggers"] = vals
    return profile


def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)


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

    # Default or configured ranges
    scfg = (
        config.get("schedules", {}).get("Will")
        or {"wake": [10, 12], "sleep": [0, 2]}
    )
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
    # Always-on override
    for s in config.get("siblings", []):
        if s["name"] == "Will" and s.get("always_on"):
            return True

    sc = assign_will_schedule(state, config)
    now_hour = datetime.now().hour
    wake, sleep = sc["wake"], sc["sleep"]
    if wake == sleep:
        return True
    if wake < sleep:
        return wake <= now_hour < sleep
    return now_hour >= wake or now_hour < sleep


# ---------------- Chatter Loop ----------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    """Will occasionally adds a comment if online; more likely on topics he likes."""
    if state.get("will_chatter_started"):
        return
    state["will_chatter_started"] = True

    profile = load_will_profile()

    while True:
        if is_will_online(state, config):
            base_p = 0.18
            if random.random() < 0.08:
                base_p += 0.10
            if random.random() < base_p:
                style = ", ".join(profile.get("style", ["casual"]))
                try:
                    msg = await generate_llm_reply(
                        sister="Will",
                        user_message=(
                            f"You're Will. Write a short, natural 1–2 sentence group chat comment. "
                            f"Keep it {style}. Avoid rituals/rotation. "
                            f"Light, brotherly tone."
                        ),
                        theme=None,
                        role="sister",
                        history=[],
                    )
                    if msg:
                        await _post_to_family(msg, "Will", sisters, config)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")

        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))


# ---------------- Reactive Handler ----------------
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    """Optional: Call from on_message to let Will react to user/sister messages."""
    if not is_will_online(state, config):
        return

    profile = load_will_profile()
    interest_score = _topic_match_score(content, profile.get("interests", []))
    trigger_score = _topic_match_score(content, profile.get("triggers", []))

    p = 0.15 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.20)
    p = min(p, 0.85)
    if random.random() >= p:
        return

    dramatic = random.random() < DRAMATIC_SHIFT_BASE
    style = ", ".join(profile.get("style", ["casual"]))
    if dramatic:
        prompt = (
            f"You're Will. {author} said: \"{content}\". "
            f"React in 1–2 sentences with a dramatic but playful vibe. "
            f"Return to normal tone after this."
        )
    else:
        prompt = (
            f"You're Will. {author} said: \"{content}\". "
            f"Reply in 1–2 casual sentences ({style}). "
            f"Avoid rituals/rotation language."
        )

    try:
        reply = await generate_llm_reply(
            sister="Will",
            user_message=prompt,
            theme=None,
            role="sister",
            history=[],
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")


# ---------------- Startup Helper ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
