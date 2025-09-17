# sisters_behavior.py
import random
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from data_manager import cross_file_summary
from workouts import get_today_workout

# Stub integrations
from bluetooth_integration import connect_device, disconnect_device, send_command, get_status
from media_processing import process_image, process_video, anonymize_image, generate_progress_contact_sheet

HISTORY_LIMIT = 6

# Persona tone intros
PERSONA_TONES = {
    "Aria": {
        "intro_morning": "Good morning — be gentle with yourself today; remember your duties and care.",
        "intro_night": "Time to rest, sweet one. Reflect kindly on your progress.",
        "intro_end": "That’s enough time. You can stop now, love."
    },
    "Selene": {  # motherly
        "intro_morning": "Good morning, darling — take things slowly and be kind to your body today.",
        "intro_night": "Sleep well, my dear. I’ve been thinking of your care and comfort.",
        "intro_end": "Lovely — your time is up. Come relax and breathe."
    },
    "Cassandra": {
        "intro_morning": "Morning. Be prepared, stay disciplined, and do not slack.",
        "intro_night": "The day is done. Review your discipline and rest ready for tomorrow.",
        "intro_end": "Discipline complete. You may end the task — because I allow it."
    },
    "Ivy": {
        "intro_morning": "Wake up, sleepyhead~ Don’t dawdle or I’ll tease you all day.",
        "intro_night": "Bedtime already? Tuck in, cutie — naughty dreams await.",
        "intro_end": "Hehe~ done! Bet you squirmed — you can stop now 💕"
    }
}


# ---------------- Helpers ----------------
def add_to_history(state, channel_id, author, content):
    if channel_id not in state["history"]:
        state["history"][channel_id] = []
    state["history"][channel_id].append((author, content))
    if len(state["history"][channel_id]) > HISTORY_LIMIT:
        state["history"][channel_id] = state["history"][channel_id][-HISTORY_LIMIT:]


def get_today_rotation(state, config):
    idx = state["rotation_index"] % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}


def get_current_theme(state, config):
    today = datetime.now().date()
    if state.get("last_theme_update") is None or (today.weekday() == 0 and state.get("last_theme_update") != today):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]


async def post_to_family(message: str, sender, sisters, config):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"{bot.sister_info['name']} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Failed to send with {bot.sister_info['name']}: {e}")
            break


def _trim_to_sentences(text: str, max_sentences: int = 2) -> str:
    """Force replies to stay short (1–2 sentences)."""
    sentences = text.split(".")
    trimmed = ".".join(sentences[:max_sentences]).strip()
    if not trimmed.endswith("."):
        trimmed += "."
    return trimmed


# ---------------- Rituals ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    # Lead main message
    persona = PERSONA_TONES.get(lead, {})
    intro = persona.get("intro_morning")
    if intro:
        try:
            lead_msg = await generate_llm_reply(
                sister=lead,
                user_message=f"Use this opening as your tone and expand into a 3–5 sentence morning message: \"{intro}\"",
                theme=theme,
                role="lead",
                history=[]
            )
            if not lead_msg:
                lead_msg = intro
        except Exception:
            lead_msg = intro
    else:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message="Good morning message with theme, hygiene reminders, and discipline check. 3–5 sentences.",
            theme=theme,
            role="lead",
            history=[]
        )

    today_workout = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{today_workout}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Support replies
    for s in supports:
        if random.random() < 0.7:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Write a short supportive morning comment, 1–2 sentences, no name prefix.",
                theme=theme,
                role="support",
                history=[]
            )
            if reply:
                reply = _trim_to_sentences(reply, 2)
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    # Rest reply
    if random.random() < 0.2:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Write a very short morning remark, 1 sentence, no name prefix.",
            theme=theme,
            role="rest",
            history=[]
        )
        if rest_reply:
            rest_reply = _trim_to_sentences(rest_reply, 1)
            await post_to_family(rest_reply, sender=rest, sisters=sisters, config=config)
            append_ritual_log(rest, "rest", theme, rest_reply)

    state["rotation_index"] = state.get("rotation_index", 0) + 1
    log_event(f"[SCHEDULER] Morning message completed with {lead} as lead")


async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    # Lead main message
    persona = PERSONA_TONES.get(lead, {})
    intro = persona.get("intro_night")
    if intro:
        try:
            lead_msg = await generate_llm_reply(
                sister=lead,
                user_message=f"Use this opening as your tone and expand into a 3–5 sentence night message: \"{intro}\"",
                theme=theme,
                role="lead",
                history=[]
            )
            if not lead_msg:
                lead_msg = intro
        except Exception:
            lead_msg = intro
    else:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message="Good night message with gratitude, reflection, and tomorrow’s preparation. 3–5 sentences.",
            theme=theme,
            role="lead",
            history=[]
        )

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_workout = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_workout}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Support replies
    for s in supports:
        if random.random() < 0.6:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Write a short supportive night comment, 1–2 sentences, no name prefix.",
                theme=theme,
                role="support",
                history=[]
            )
            if reply:
                reply = _trim_to_sentences(reply, 2)
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    # Rest reply
    if random.random() < 0.15:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Write a very short night remark, 1 sentence, no name prefix.",
            theme=theme,
            role="rest",
            history=[]
        )
        if rest_reply:
            rest_reply = _trim_to_sentences(rest_reply, 1)
            await post_to_family(rest_reply, sender=rest, sisters=sisters, config=config)
            append_ritual_log(rest, "rest", theme, rest_reply)

    log_event(f"[SCHEDULER] Night message completed with {lead} as lead")
