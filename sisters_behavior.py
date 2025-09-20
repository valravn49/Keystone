# sisters_behavior.py
import random
import re
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout  # ✅ new rotation system

# Persona tones
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

# ---------------- Helpers ----------------
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


async def post_to_family(message: str, sender, sisters, config):
    for bot in sisters:
        if bot.is_ready():
            if not sender or bot.sister_info["name"] == sender:
                try:
                    channel = bot.get_channel(config["family_group_channel"])
                    if channel:
                        await channel.send(message)
                        log_event(f"{bot.sister_info['name']} posted: {message}")
                except Exception as e:
                    log_event(f"[ERROR] Failed send {bot.sister_info['name']}: {e}")
                break

# ---------------- Rituals ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    persona = PERSONA_TONES.get(lead, {})
    intro = persona.get("intro_morning")

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

    # ✅ Add today’s workout
    workout_block = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Support messages
    for s in supports:
        if random.random() < 0.7:
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

    persona = PERSONA_TONES.get(lead, {})
    intro = persona.get("intro_night")

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

    # ✅ Add tomorrow’s workout
    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Supporter reflections
    for s in supports:
        if random.random() < 0.6:
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

# ---------------- Scheduler ----------------
async def scheduler_loop(state, config, sisters):
    """Run daily tasks at fixed times (07:00 and 21:00)."""
    while True:
        now = datetime.now()
        target_times = [
            (7, 0, send_morning_message),
            (21, 0, send_night_message),
        ]
        for hour, minute, func in target_times:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target < now:
                target += timedelta(days=1)
            wait_time = (target - now).total_seconds()
            await asyncio.sleep(wait_time)
            await func(state, config, sisters)
