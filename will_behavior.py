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


# ---------------- Persona wrapper ----------------
async def _persona_reply(base_prompt: str, role: str, config: Dict, history: List):
    """Force Will’s replies to respect his config personality + swearing rules."""
    will_cfg = next((s for s in config["rotation"] if s["name"] == "Will"), {})
    personality = will_cfg.get("personality", "Casual, nerdy, sometimes dramatic.")
    allow_swear = will_cfg.get("swearing_allowed", True)

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"{'Swearing is allowed if it feels natural.' if allow_swear else 'Do not swear.'} "
        f"{base_prompt}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role=role,
        history=history,
    )


# ---------------- Schedule ----------------
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "will_schedule"
    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]

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
                    msg = await _persona_reply(
                        f"Write a short, natural 1–2 sentence group chat comment. "
                        f"Keep it {style}. Avoid rituals/rotation. "
                        f"Light, brotherly tone.",
                        role="support",
                        config=config,
                        history=[],
                    )
                    if msg:
                        await _post_to_family(msg, "Will", sisters, config)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")

        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))


# ---------------- Reactive Handler ----------------
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
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
        base_prompt = (
            f"{author} said: \"{content}\". "
            f"React in 1–2 sentences with a dramatic but playful vibe. "
            f"Return to normal tone after this."
        )
    else:
        base_prompt = (
            f"{author} said: \"{content}\". "
            f"Reply in 1–2 casual sentences ({style}). "
            f"Avoid rituals/rotation language."
        )

    try:
        reply = await _persona_reply(
            base_prompt, role="support", config=config, history=[]
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
