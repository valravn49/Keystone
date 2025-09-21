# sisters_behavior.py
import random
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# Persona tones for rituals
PERSONA_TONES = {
    "Aria": {
        "intro_morning": "Good morning — be gentle with yourself today; remember your duties and care.",
        "intro_night": "Time to rest, sweet one. Reflect kindly on your progress.",
    },
    "Selene": {
        "intro_morning": "Good morning, darling — take things slowly and be kind to your body today.",
        "intro_night": "Sleep well, my dear. I’ve been thinking of your care and comfort.",
    },
    "Cassandra": {
        "intro_morning": "Morning. Be prepared, stay disciplined, and do not slack.",
        "intro_night": "The day is done. Review your discipline and rest ready for tomorrow.",
    },
    "Ivy": {
        "intro_morning": "Wake up, sleepyhead~ Don’t dawdle or I’ll tease you all day.",
        "intro_night": "Bedtime already? Tuck in, cutie — naughty dreams await.",
    },
}

# ---------------- Rotation & Theme ----------------
def get_today_rotation(state, config):
    idx = state["rotation_index"] % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def get_current_theme(state, config):
    today = datetime.now().date()
    if state.get("last_theme_update") is None or (
        today.weekday() == 0 and state.get("last_theme_update") != today
    ):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]

# ---------------- Daily Schedules ----------------
def assign_schedule(state, config, sister_name: str):
    """Assign today's wake/sleep for a sister if not already stored."""
    today = datetime.now().date()
    key = f"{sister_name}_schedule"
    if state.get(f"{key}_date") == today and key in state:
        return state[key]

    scfg = config.get("schedules", {}).get(sister_name, {"wake": [6, 8], "sleep": [22, 23]})
    wake_rng = scfg.get("wake", [6, 8])
    sleep_rng = scfg.get("sleep", [22, 23])

    wake_hr = random.randint(wake_rng[0], wake_rng[1])
    sleep_hr = random.randint(sleep_rng[0], sleep_rng[1])

    schedule = {"wake": wake_hr, "sleep": sleep_hr}
    state[key] = schedule
    state[f"{key}_date"] = today
    return schedule

def is_awake(state, config, sister_name: str, lead_name: str):
    """Check if a sister is awake unless she’s lead (then always awake)."""
    if sister_name == lead_name:
        return True

    sc = assign_schedule(state, config, sister_name)
    now_hour = datetime.now().hour
    wake, sleep = sc["wake"], sc["sleep"]

    if wake < sleep:
        return wake <= now_hour < sleep
    else:
        # Handles overnight schedules like 23 → 2
        return now_hour >= wake or now_hour < sleep

# ---------------- Messaging ----------------
async def post_to_family(message: str, sender, sisters, config):
    """Send to family channel through the correct bot instance."""
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Failed send {sender}: {e}")
            break

# ---------------- Rituals ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Good morning.")
    try:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message=f"{lead}: Expand this into a warm 3–5 sentence morning greeting. \"{intro}\"",
            theme=theme,
            role="lead",
            history=[],
        )
    except Exception:
        lead_msg = intro

    workout_block = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if is_awake(state, config, s, lead) and random.random() < 0.7:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Short supportive morning comment, 1–2 sentences.",
                theme=theme,
                role="support",
                history=[],
            )
            if reply:
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    state["rotation_index"] = state.get("rotation_index", 0) + 1

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Good night.")
    try:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message=f"{lead}: Expand this into a thoughtful 3–5 sentence night reflection. \"{intro}\"",
            theme=theme,
            role="lead",
            history=[],
        )
    except Exception:
        lead_msg = intro

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if is_awake(state, config, s, lead) and random.random() < 0.6:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Short supportive night comment, 1–2 sentences.",
                theme=theme,
                role="support",
                history=[],
            )
            if reply:
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

# ---------------- Interaction ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    """Allow siblings to interact with each other if awake."""
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(state, config, sname, lead):
            continue

        chance = 0.2
        if sname == lead:
            chance = 0.8
        elif sname in rotation["supports"]:
            chance = 0.5
        elif sname == rotation["rest"]:
            chance = 0.1

        if random.random() < chance:
            try:
                reply = await generate_llm_reply(
                    sister=sname,
                    user_message=f"Reply to {author}: {content}",
                    theme=theme,
                    role="support",
                    history=[],
                )
                if reply:
                    await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                    log_event(f"[CHAT] {sname} → {author}: {reply}")
            except Exception as e:
                log_event(f"[ERROR] Sister reply failed for {sname}: {e}")
