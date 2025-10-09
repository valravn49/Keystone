# will_behavior.py
import os
import json
import random
import asyncio
from datetime import datetime
import pytz
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# ---------------------------------------------------------------------
# AEDT Local Time Zone
# ---------------------------------------------------------------------
AEDT = pytz.timezone("Australia/Sydney")

# ---------------------------------------------------------------------
# File Paths
# ---------------------------------------------------------------------
PERSONALITY_PATH = "/Autonomy/personalities/Will_Personality.json"
MEMORY_PATH = "/Autonomy/memory/Will_Memory.json"
REFINEMENTS_LOG = "/mnt/data/Sisters_Refinements_Log.txt"

# ---------------------------------------------------------------------
# Defaults and constants
# ---------------------------------------------------------------------
WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

INTEREST_HIT_BOOST = 0.35
IVY_BOOST = 0.25
RANT_CHANCE = 0.10

# ---------------------------------------------------------------------
# Load & Save Helpers
# ---------------------------------------------------------------------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Failed reading {path}: {e}")
    return default


def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Failed writing {path}: {e}")


def _add_refinement_log(msg: str):
    timestamp = datetime.now(AEDT).isoformat(timespec="seconds")
    try:
        with open(REFINEMENTS_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Will: {msg}\n")
    except Exception:
        pass

# ---------------------------------------------------------------------
# Profile & Memory
# ---------------------------------------------------------------------
def load_will_personality() -> dict:
    default = {
        "name": "Will",
        "interests": ["tech", "games", "anime", "music"],
        "dislikes": ["drama"],
        "style": ["casual", "timid", "sometimes playful"],
        "growth_path": {"confidence": 0.4, "introversion": 0.8, "warmth": 0.5},
    }
    return _load_json(PERSONALITY_PATH, default)


def load_will_memory() -> dict:
    default = {"projects": {}, "recent_notes": [], "last_outfit_prompt": None}
    return _load_json(MEMORY_PATH, default)


def save_will_memory(mem: dict):
    _save_json(MEMORY_PATH, mem)

# ---------------------------------------------------------------------
# Time-based schedule
# ---------------------------------------------------------------------
def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep:
        return True
    if wake < sleep:
        return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep


def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key = "will_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and state.get(key):
        return state[key]

    scfg = config.get("schedules", {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        return random.randint(lo, hi) if hi >= lo else lo
    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key] = schedule
    state[kd] = today
    return schedule


def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------------------------------------------------------------------
# Outfit System (masc vs. fem)
# ---------------------------------------------------------------------
def _select_outfit(persona: dict, memory: dict) -> str:
    """
    Will wears masculine outfit if timid (default),
    or switches to feminine outfit when confident or playful.
    """
    conf = persona.get("growth_path", {}).get("confidence", 0.4)
    intro = persona.get("growth_path", {}).get("introversion", 0.8)

    bold = conf > 0.6 and intro < 0.7
    if bold:
        outfit = "a soft feminine look — maybe a cropped hoodie and fitted jeans"
    else:
        outfit = "his usual comfy masculine style — hoodie, tee, and loose jeans"

    # Occasionally vary the description slightly
    if random.random() < 0.3:
        outfit += random.choice([
            ", headphones hanging around his neck",
            ", sleeves pushed up to his elbows",
            ", sneakers slightly mismatched",
            ", hair a bit messy from coding too late",
        ])

    memory["last_outfit_prompt"] = outfit
    save_will_memory(memory)
    _add_refinement_log(f"Updated outfit: {outfit}")
    return outfit

# ---------------------------------------------------------------------
# Persona generator
# ---------------------------------------------------------------------
async def _persona_reply(
    base_prompt: str,
    rant: bool = False,
    timid: bool = True,
    state: Dict = None,
    config: Dict = None,
) -> str:
    persona = load_will_personality()
    memory = load_will_memory()
    outfit = memory.get("last_outfit_prompt") or _select_outfit(persona, memory)

    tone = "hesitant, warm, and softly spoken" if timid else "animated but slightly nervous"
    outfit_hint = ""
    if random.random() < 0.4:
        outfit_hint = f" If it feels natural, mention what you’re wearing today ({outfit})."

    style = ", ".join(persona.get("style", []))
    prompt = (
        f"You are Will — a shy, nerdy younger brother who tries to engage softly. "
        f"Style: {style}. Tone: {tone}.{outfit_hint} "
        f"{base_prompt}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------------------------------------------------------------
# Background chatter loop
# ---------------------------------------------------------------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"):
        return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.1
            if random.random() < 0.05:
                base_p += 0.1
            if random.random() < base_p:
                rant_mode = random.random() < RANT_CHANCE
                timid_mode = random.random() > 0.25  # 75% timid
                try:
                    msg = await _persona_reply(
                        "Add a small, natural group chat comment. Keep it sibling-like and shy.",
                        rant=rant_mode,
                        timid=timid_mode,
                        state=state,
                        config=config,
                    )
                    if msg:
                        await _post_to_family(msg, "Will", sisters, config)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------------------------------------------------------------------
# Message handling (reactive)
# ---------------------------------------------------------------------
async def _post_to_family(message: str, sender: str, sisters, config: Dict):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break

def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)

async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config):
        return

    persona = load_will_personality()
    interest_score = _topic_match_score(content, persona.get("interests", []))
    trigger_score = _topic_match_score(content, persona.get("triggers", ["games", "anime", "tech"]))

    p = 0.12 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.2)
    if author == "Ivy":
        p += IVY_BOOST
    if "will" in content.lower():
        p = 1.0
    p = min(p, 0.9)

    if random.random() >= p:
        return

    rant_mode = random.random() < RANT_CHANCE
    timid_mode = random.random() > 0.25
    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply naturally as Will, in your usual shy, slightly awkward sibling tone.',
            rant=rant_mode,
            timid=timid_mode,
            state=state,
            config=config,
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

# ---------------------------------------------------------------------
# Startup Integration
# ---------------------------------------------------------------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
