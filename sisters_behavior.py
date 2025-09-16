import random
import time
import re
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_conversation_log, append_ritual_log
from data_manager import parse_data_command, cross_file_summary
from workouts import get_today_workout  # ✅ workout cycle integration

# Stub integrations
from bluetooth_integration import connect_device, disconnect_device, send_command, get_status
from media_processing import process_image, process_video, anonymize_image, generate_progress_contact_sheet

HISTORY_LIMIT = 6
COOLDOWN_SECONDS = 10
MESSAGE_LIMIT = 5
MESSAGE_WINDOW = 60

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
        if bot.is_ready():
            if not sender or bot.sister_info["name"] == sender:
                try:
                    channel = bot.get_channel(config["family_group_channel"])
                    if channel:
                        await channel.send(message)
                        log_event(f"{bot.sister_info['name']} posted: {message}")
                    else:
                        print(f"[ERROR] Channel {config['family_group_channel']} not found for {bot.sister_info['name']}")
                except Exception as e:
                    print(f"[ERROR] Failed to send with {bot.sister_info['name']}: {e}")
                break


# ---------------- Duration extraction ----------------
_DURATION_REGEX = re.compile(r"(\d+)\s*(hours|hour|hrs|hr|h|minutes|minute|mins|min|m)\b", re.I)

def _extract_duration_seconds(text: str):
    m = _DURATION_REGEX.search(text)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("h"):
        return val * 3600
    return val * 60

def _remove_duration_phrases(text: str):
    return _DURATION_REGEX.sub("", text).strip()


async def _schedule_spontaneous_end(state, sisters, config, sister_name, duration_seconds):
    async def _wait_and_notify():
        try:
            await asyncio.sleep(duration_seconds)
            persona = PERSONA_TONES.get(sister_name, {})
            intro = persona.get("intro_end", "Your task is complete. You may stop now.")

            if random.random() < 0.5:
                line = intro
            else:
                try:
                    expansion = await generate_llm_reply(
                        sister=sister_name,
                        user_message=f"{sister_name}: Expand this 1-line closing in your voice: \"{intro}\" Keep it 1 short sentence.",
                        theme=None,
                        role="lead",
                        history=[]
                    )
                    line = expansion if expansion else intro
                except Exception:
                    line = intro

            end_msg = f"{sister_name}: {line}"
            await post_to_family(end_msg, sender=sister_name, sisters=sisters, config=config)
            log_event(f"[TASK-END] {sister_name} notified task end (persona-mixed).")
        except asyncio.CancelledError:
            log_event(f"[TASK-END] Cancelled end notification for {sister_name}.")
        except Exception as e:
            log_event(f"[TASK-END] Error notifying end: {e}")

    t = asyncio.create_task(_wait_and_notify())
    key = f"{datetime.now().date().isoformat()}_{sister_name}"
    state.setdefault("spontaneous_end_tasks", {})[key] = t


# ---------------- Rituals ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    persona = PERSONA_TONES.get(lead, {})
    intro = persona.get("intro_morning")

    if intro:
        try:
            lead_msg = await generate_llm_reply(
                sister=lead,
                user_message=f"{lead}: Use this opening as your tone and expand into a 3-5 sentence morning message. \"{intro}\"",
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
            user_message="Good morning message: include theme, hygiene reminders, and discipline check. Write 3–5 sentences.",
            theme=theme,
            role="lead",
            history=[]
        )

    # ✅ Add today's workout
    today_workout = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{today_workout}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if random.random() < 0.7:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Short supportive morning comment, 1–2 sentences.",
                theme=theme,
                role="support",
                history=[]
            )
            if reply:
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    if random.random() < 0.2:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Quiet short morning remark, 1 sentence.",
            theme=theme,
            role="rest",
            history=[]
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest, sisters=sisters, config=config)
            append_ritual_log(rest, "rest", theme, rest_reply)

    state["rotation_index"] = state.get("rotation_index", 0) + 1
    log_event(f"[SCHEDULER] Morning message completed with {lead} as lead")


async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    persona = PERSONA_TONES.get(lead, {})
    intro = persona.get("intro_night")

    if intro:
        try:
            lead_msg = await generate_llm_reply(
                sister=lead,
                user_message=f"{lead}: Use this opening as your tone and expand into a 3-5 sentence night message. \"{intro}\"",
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
            user_message="Good night message: thank supporters, ask reflection, remind about outfits, and plug/service tasks. Write 3–5 sentences.",
            theme=theme,
            role="lead",
            history=[]
        )

    # ✅ Add tomorrow's workout
    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_workout = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_workout}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if random.random() < 0.6:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Short supportive night comment, 1–2 sentences.",
                theme=theme,
                role="support",
                history=[]
            )
            if reply:
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    if random.random() < 0.15:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Brief quiet night remark, 1 sentence.",
            theme=theme,
            role="rest",
            history=[]
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest, sisters=sisters, config=config)
            append_ritual_log(rest, "rest", theme, rest_reply)

    log_event(f"[SCHEDULER] Night message completed with {lead} as lead")
