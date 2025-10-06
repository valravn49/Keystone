import json
import os
import random
import asyncio
from datetime import datetime, timedelta, time

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout
from outfit_manager import maybe_generate_outfit_image  # 🪞 Outfit integration

# ---------------------------------------------------------------------------
# Personality tones for ritual OPENERS
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Helpers: profiles, memory, awake checks
# ---------------------------------------------------------------------------

def _profile_path(name: str) -> str:
    return f"/mnt/data/{name}_Personality.json"

def _memory_path(name: str) -> str:
    return f"/mnt/data/{name}_Memory.json"

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Failed reading {path}: {e}")
    return default

def load_persona(name: str) -> dict:
    defaults = {"name": name, "likes": [], "dislikes": [], "speech_examples": [], "core_personality": ""}
    data = _load_json(_profile_path(name), defaults)
    for key in defaults:
        data.setdefault(key, defaults[key])
    return data

def load_memory(name: str) -> dict:
    data = _load_json(_memory_path(name), {"projects": {}, "recent_notes": []})
    data.setdefault("projects", {})
    data.setdefault("recent_notes", [])
    return data

def save_memory(name: str, memo: dict) -> None:
    try:
        path = _memory_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memo, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Failed writing memory for {name}: {e}")

def _assign_today_schedule(name: str, state: dict, config: dict):
    key = f"{name}_schedule"
    kd = f"{key}_date"
    today = datetime.now().date()
    if state.get(kd) == today and key in state:
        return state[key]

    sch = (config.get("schedules", {}) or {}).get(name, {"wake": [6, 8], "sleep": [22, 23]})
    def pick(span): return random.randint(int(span[0]), int(span[1]))
    schedule = {"wake": pick(sch["wake"]), "sleep": pick(sch["sleep"])}
    state[key], state[kd] = schedule, today
    return schedule

def is_awake(sister_info, lead_name, state=None, config=None):
    if sister_info["name"] == lead_name:
        return True
    sc = _assign_today_schedule(sister_info["name"], state, config)
    now = datetime.now().hour
    w, s = sc["wake"], sc["sleep"]
    return (w <= now < s) if w < s else (now >= w or now < s)

def get_today_rotation(state, config):
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation(state, config):
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])

# ---------------------------------------------------------------------------
# Persona Reply Wrapper
# ---------------------------------------------------------------------------

async def _persona_reply(sname, role, base_prompt, theme, history, config, mode="default", address_to=None):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    prompt = (
        f"You are {sname}. Personality: {personality}. Tone: {role}. "
        f"Style: {mode}. {'Swearing allowed.' if allow_swear else 'No swearing.'} "
        f"Speak casually like siblings — teasing or supportive, natural tone. "
        f"{f'Address {address_to} directly if it fits.' if address_to else ''} "
        f"{base_prompt}"
    )
    return await generate_llm_reply(
        sister=sname, user_message=prompt, theme=theme, role=role, history=history
    )

# ---------------------------------------------------------------------------
# Rituals
# ---------------------------------------------------------------------------

async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme, lead = (get_current_theme(state, config), rotation["lead"])
    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_morning", ["Morning."]))

    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 sentences as a brisk morning sibling greeting. Start from "{opener}"',
            theme, [], config, mode="story"
        )
    except Exception:
        lead_msg = opener

    workout_block = get_today_workout()
    if workout_block:
        lead_msg += f"\n\n🏋️ Today’s workout: {workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    await maybe_generate_outfit_image(lead, lead_msg, sisters, config, state)
    append_ritual_log(lead, "lead", theme, lead_msg)
    advance_rotation(state, config)

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme, lead = (get_current_theme(state, config), rotation["lead"])
    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_night", ["Night."]))

    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 sentences as a gentle sibling reflection. Start from "{opener}"',
            theme, [], config, mode="story"
        )
    except Exception:
        lead_msg = opener

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    if tomorrow_block:
        lead_msg += f"\n\n🌙 Tomorrow’s workout: {tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    await maybe_generate_outfit_image(lead, lead_msg, sisters, config, state)
    append_ritual_log(lead, "lead", theme, lead_msg)

# ---------------------------------------------------------------------------
# Spontaneous
# ---------------------------------------------------------------------------

async def send_spontaneous_task(state, config, sisters):
    now = datetime.now()
    sc = state.setdefault("shared_context", {})
    if "last_spontaneous_ts" in sc and (now - sc["last_spontaneous_ts"]).total_seconds() < random.randint(2600, 5700):
        return

    rotation = get_today_rotation(state, config)
    theme, lead = get_current_theme(state, config), rotation["lead"]
    awake = [b.sister_info["name"] for b in sisters if is_awake(b.sister_info, lead, state, config)]
    if not awake:
        return

    speaker = random.choice(awake)
    msg = await _persona_reply(
        speaker, "support", "Say something casual to start conversation.", theme, [], config, mode="default"
    )
    if msg:
        await post_to_family(msg, sender=speaker, sisters=sisters, config=config)
        await maybe_generate_outfit_image(speaker, msg, sisters, config, state)
        log_event(f"[SPONTANEOUS] {speaker}: {msg}")
        sc["last_spontaneous_ts"] = now

# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------

async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme, lead = get_current_theme(state, config), rotation["lead"]

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author or not is_awake(bot.sister_info, lead, state, config):
            continue

        chance = 0.25
        if sname == lead:
            chance = 0.8
        elif sname in rotation["supports"]:
            chance = 0.5
        elif sname == rotation["rest"]:
            chance = 0.2

        if sname.lower() in content.lower() or "everyone" in content.lower():
            chance = 1.0

        if random.random() < chance:
            reply = await _persona_reply(
                sname, "support",
                f'Reply to {author}: "{content}". Keep it short, teasing or kind like siblings.',
                theme, [], config, mode=random.choice(["tease", "support", "story"]), address_to=author
            )
            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                await maybe_generate_outfit_image(sname, reply, sisters, config, state)
                log_event(f"[CHAT] {sname} → {author}: {reply}")
