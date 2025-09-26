import os
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# Will's profile + defaults
DEFAULT_PROFILE_PATHS = ["data/Will_Profile.txt", "/mnt/data/Will_Profile.txt"]

WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

INTEREST_HIT_BOOST = 0.35
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.08

WILL_FAVORITES_POOL = [
    "retro consoles", "anime OSTs", "indie games", "cozy RPGs", "streaming marathons"
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
        "interests": ["games", "anime", "tech"],
        "dislikes": ["drama"],
        "style": ["shy", "timid", "casual"],
        "triggers": ["nostalgia", "memes"],
        "favorites": WILL_FAVORITES_POOL,
    }
    return profile

# ---------------- Persona reply ----------------
async def _persona_reply(base_prompt: str, rant: bool = False) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["shy"]))
    personality = "Timid, shy, nerdy younger brother who hedges and doubts himself."

    extra = (
        "Keep it soft, shy, with hesitation. Maybe include phrases like 'uh', 'I guess', 'not sure but...'."
    )

    if rant:
        extra = "Make it a shy rant: apologetic, overexplaining, and nervous."

    prompt = (
        f"You are Will. Personality: {personality}. Style: {style}. "
        f"{base_prompt} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------- Messaging ----------------
async def _post_to_family(message: str, sisters, config: Dict):
    for bot in sisters:
        if bot.sister_info["name"] == "Will" and bot.is_ready():
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"Will posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break

# ---------------- Handler ----------------
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    lowered = content.lower()
    direct_question = "?" in content and "will" in lowered
    ivy_boost = (author.lower().startswith("ivy") or "ivy" in lowered)

    # ✅ Always respond if Will is directly asked
    if direct_question:
        reply = await _persona_reply(
            f"{author} asked Will: \"{content}\". Reply shyly and nervously, like you're a bit unsure but want to help."
        )
        if reply:
            await _post_to_family(reply, sisters, config)
        return

    # ✅ Ivy boost: much higher chance to respond to Ivy
    base_p = 0.15
    if ivy_boost:
        base_p *= 3  # 3x chance if Ivy is involved
        if random.random() < 0.9:  # almost always reply if Ivy speaks to him
            reply = await _persona_reply(
                f"Ivy said: \"{content}\". Reply shyly, maybe flustered, like you're caught off guard but want to engage."
            )
            if reply:
                await _post_to_family(reply, sisters, config)
            return

    # fallback: occasional reactive comments
    if random.random() < base_p:
        reply = await _persona_reply(f"{author} said: \"{content}\". Reply timidly.")
        if reply:
            await _post_to_family(reply, sisters, config)

# ---------------- Startup ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    state["will_ready"] = True
