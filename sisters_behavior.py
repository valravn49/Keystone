# sisters_behavior.py
import os
import json
import random
import asyncio
from datetime import datetime, timedelta
import pytz

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# AEDT time zone for consistent local scheduling
AEDT = pytz.timezone("Australia/Sydney")

# ---------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------
PERSONALITY_PATH = "/Autonomy/personalities"
MEMORY_PATH = "/Autonomy/memory"
REFINEMENTS_LOG = "/mnt/data/Sisters_Refinements_Log.txt"

# ---------------------------------------------------------------------
# Personality tones for ritual openers
# ---------------------------------------------------------------------
PERSONA_TONES = {
    "Aria": {
        "intro_morning": [
            "Morning — I stayed up too late reorganizing notes again.",
            "Good morning. I’m trying to keep it calm today.",
            "Morning, coffee first… then brain.",
        ],
        "intro_night": [
            "Time to rest. I’ll probably read a little before bed.",
            "Good night — today was steady enough.",
            "Lights out soon. Quiet is good.",
        ],
    },
    "Selene": {
        "intro_morning": [
            "Morning, darlings — eat something before you rush off.",
            "Good morning — start slow, breathe.",
            "Morning, loves. Remember water and breakfast.",
        ],
        "intro_night": [
            "Good night, sweet ones. Don’t forget blankets.",
            "Sleep well — be soft with yourselves.",
            "Night night — proud of little things today.",
        ],
    },
    "Cassandra": {
        "intro_morning": [
            "Up. The day won’t wait.",
            "Morning. Let’s keep it tight.",
            "Move. Momentum matters.",
        ],
        "intro_night": [
            "The day’s done. Don’t slack tomorrow.",
            "Turn in. Review and reset.",
            "Done. Sleep on it, wake sharper.",
        ],
    },
    "Ivy": {
        "intro_morning": [
            "Ughhh are we awake? Fine — hi~",
            "Morning, gremlins. No dawdling or I’ll tease.",
            "Good morning~ I call dibs on the mirror.",
        ],
        "intro_night": [
            "Night night! No snoring, I’m serious (I’m not).",
            "Okay bedtime — I’m stealing the fluffy blanket.",
            "Sleep tight~ I’m haunting your dreams.",
        ],
    },
}

# ---------------------------------------------------------------------
# Helper functions for loading data
# ---------------------------------------------------------------------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] JSON load failed {path}: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] JSON write failed {path}: {e}")

def load_personality(name: str) -> dict:
    path = os.path.join(PERSONALITY_PATH, f"{name}_Personality.json")
    return _load_json(path, {"name": name, "likes": [], "dislikes": [], "core_personality": ""})

def load_memory(name: str) -> dict:
    path = os.path.join(MEMORY_PATH, f"{name}_Memory.json")
    return _load_json(path, {"projects": {}, "recent_notes": [], "last_outfit_prompt": None})

def save_memory(name: str, data: dict):
    path = os.path.join(MEMORY_PATH, f"{name}_Memory.json")
    _save_json(path, data)

def _add_refinement_log(name: str, msg: str):
    timestamp = datetime.now(AEDT).isoformat(timespec="seconds")
    try:
        with open(REFINEMENTS_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {name}: {msg}\n")
    except Exception:
        pass

# ---------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------
def get_today_rotation(state, config):
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation(state, config):
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])

def get_current_theme(state, config):
    today = datetime.now(AEDT).date()
    if state.get("last_theme_update") is None or (
        today.weekday() == 0 and state.get("last_theme_update") != today
    ):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]

# ---------------------------------------------------------------------
# Persona wrapper (with outfit mention integration)
# ---------------------------------------------------------------------
async def _persona_reply(name, role, base_prompt, theme, history, config, mode="default"):
    persona = load_personality(name)
    memory = load_memory(name)
    outfit = memory.get("last_outfit_prompt")

    # 30% chance to mention outfit if it exists
    outfit_hint = ""
    if outfit and random.random() < 0.3:
        outfit_hint = f" Mention casually what you're wearing today ({outfit}) if it fits the tone."

    tone_map = {
        "support": "encouraging, warm, maybe teasing",
        "tease": "playful or bratty sibling energy",
        "challenge": "blunt but affectionate honesty",
        "story": "reflective and natural sibling tone",
        "default": "casual, real sibling banter",
    }

    prompt = (
        f"You are {name}. Personality: {persona.get('core_personality','')}. "
        f"Talk naturally like a sibling — informal, teasing, kind, quick replies. "
        f"Mode: {tone_map.get(mode, 'casual')}. "
        f"{outfit_hint} {base_prompt}"
    )

    return await generate_llm_reply(
        sister=name,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )

# ---------------------------------------------------------------------
# Ritual messages
# ---------------------------------------------------------------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    intro = random.choice(PERSONA_TONES.get(lead, {}).get("intro_morning", ["Morning."]))
    try:
        msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 sentences for a morning sibling greeting. Start with: "{intro}"',
            theme, [], config, mode="story",
        )
    except Exception:
        msg = intro

    workout = get_today_workout()
    if workout:
        msg += f"\n\n🏋️ Today’s workout: {workout}"

    await _post_to_family(msg, lead, sisters, config)
    append_ritual_log(lead, "lead", theme, msg)
    advance_rotation(state, config)

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    intro = random.choice(PERSONA_TONES.get(lead, {}).get("intro_night", ["Night."]))
    try:
        msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 sentences for a thoughtful night sibling reflection. Start with: "{intro}"',
            theme, [], config, mode="story",
        )
    except Exception:
        msg = intro

    tomorrow = datetime.now(AEDT).date() + timedelta(days=1)
    next_workout = get_today_workout(tomorrow)
    if next_workout:
        msg += f"\n\n🌙 Tomorrow’s workout: {next_workout}"

    await _post_to_family(msg, lead, sisters, config)
    append_ritual_log(lead, "lead", theme, msg)

# ---------------------------------------------------------------------
# Messaging / spontaneous chat
# ---------------------------------------------------------------------
async def _post_to_family(message, sender, sisters, config):
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Failed to send for {sender}: {e}")
            break

async def send_spontaneous_task(state, config, sisters):
    """Natural sibling chat trigger with outfit, media, or project mentions."""
    now = datetime.now(AEDT)
    last = state.get("last_spontaneous_ts")
    if last and (now - last).total_seconds() < random.randint(2500, 5500):
        return

    awake = [bot.sister_info["name"] for bot in sisters]
    if not awake:
        return

    speaker = random.choice(awake)
    mode = random.choice(["tease", "support", "story", "default"])
    theme = get_current_theme(state, config)

    base = "Start a short, natural sibling conversation. It can include a casual check-in or tease."
    msg = await _persona_reply(speaker, "support", base, theme, [], config, mode=mode)
    if msg:
        await _post_to_family(msg, speaker, sisters, config)
        state["last_spontaneous_ts"] = now
        log_event(f"[SPONTANEOUS] {speaker}: {msg}")
