import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event
from relationships import adjust_relationship

# ---------------- File Paths ----------------
PERSONALITY_FILE = "Autonomy/Personalities/Will.json"
MEMORY_FILE = "Autonomy/memory/Will.json"

# Chatter pacing (seconds)
WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

# Probability constants
INTEREST_HIT_BOOST = 0.35
IVY_BOOST = 0.25
RANT_CHANCE = 0.10


# ---------------- JSON Helpers ----------------
def load_json(path: str, default: Dict) -> Dict:
    """Load JSON file or create with default if missing."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_event(f"[ERROR] Failed to load {path}: {e}")
        return default


def save_json(path: str, data: Dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log_event(f"[ERROR] Failed to save {path}: {e}")


# ---------------- Personality / Memory ----------------
def load_will_profile() -> Dict:
    defaults = {
        "name": "Will",
        "interests": ["tech", "games", "anime", "music"],
        "dislikes": ["drama"],
        "style": ["casual", "timid", "sometimes playful"],
        "triggers": ["hype", "memes", "nostalgia", "Ivy teasing"],
        "favorites": ["Legend of Zelda", "Final Fantasy", "League of Legends"],
        "speech_patterns": {
            "timid": "hesitant, soft-spoken, sometimes trailing off",
            "outgoing": "excited, fast, sometimes overshares when flustered"
        },
        "swearing_allowed": True
    }
    return load_json(PERSONALITY_FILE, defaults)


def load_will_memory() -> Dict:
    defaults = {
        "last_active": None,
        "mood": "neutral",
        "bad_mood": False,
        "rotation_index": 0,
        "theme_index": 0,
        "relationships": {},
        "refinements": [],
        "spontaneous_spoken_today": {},
        "will_schedule": {"wake": 11, "sleep": 1}
    }
    return load_json(MEMORY_FILE, defaults)


def save_will_memory(data: Dict):
    save_json(MEMORY_FILE, data)


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
async def _persona_reply(base_prompt: str, rant: bool = False, timid: bool = True) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", []))
    personality = "Shy, nerdy, often hesitant but occasionally playful or dramatic."

    tone = "hesitant, soft-spoken" if timid else "more outgoing and expressive"
    extra = (
        f"Make it ranty/animated, 2–3 sentences, playful but dramatic."
        if rant else
        f"Keep it short (1–2 sentences), {style}, brotherly but {tone}."
    )

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"Speech style: {tone}. "
        f"{base_prompt} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sibling",
        history=[],
    )


# ---------------- Schedule ----------------
def assign_will_schedule(state: Dict, config: Dict):
    mem = load_will_memory()
    today = datetime.now().date()

    if mem.get("schedule_date") == str(today):
        return mem["will_schedule"]

    scfg = config.get("schedules", {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    wake = random.randint(*scfg.get("wake", [10, 12]))
    sleep = random.randint(*scfg.get("sleep", [0, 2]))

    mem["will_schedule"] = {"wake": wake, "sleep": sleep}
    mem["schedule_date"] = str(today)
    save_will_memory(mem)

    return mem["will_schedule"]


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
    mem = load_will_memory()
    if mem.get("chatter_started"):
        return
    mem["chatter_started"] = True
    save_will_memory(mem)

    while True:
        if is_will_online(state, config):
            if random.random() < 0.12:  # base shy chance
                rant_mode = random.random() < RANT_CHANCE
                timid_mode = random.random() > 0.3
                try:
                    msg = await _persona_reply(
                        "Write a group chat comment.",
                        rant=rant_mode, timid=timid_mode
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

    p = 0.10 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.20)
    if author == "Ivy":
        p += IVY_BOOST
    p = min(p, 0.85)

    if "will" in content.lower():
        p = 1.0

    if random.random() >= p:
        return

    rant_mode = random.random() < RANT_CHANCE
    timid_mode = random.random() > 0.3

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\". Reply like Will would.",
            rant=rant_mode, timid=timid_mode
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config)
            if author == "Ivy":
                adjust_relationship(state, "Will", "Ivy", "affection", +0.08)
            else:
                adjust_relationship(state, "Will", author, "affection", +0.05)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")


# ---------------- Startup ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    mem = load_will_memory()
    if not mem.get("chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))


# ---------------- Topic Helper ----------------
def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)
