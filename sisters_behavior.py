# sisters_behavior.py
import random
import time
import re
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_conversation_log, append_ritual_log
from data_manager import parse_data_command, cross_file_summary
from workouts import get_today_workout

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

# ---------------- Persona + Swearing ----------------
def build_persona_hint(sister_name: str, style_hint: str, config: dict) -> str:
    """Build persona prompt with optional swearing allowance."""
    sister = next((s for s in config["rotation"] if s["name"] == sister_name), None)
    if not sister:
        return style_hint

    allow_swearing = sister.get("allow_swearing", False)
    personality = sister.get("personality", "")

    hint = f"Stay in character as {sister_name}. Personality: {personality}. {style_hint}"
    if allow_swearing:
        hint += " You may swear naturally if it fits your personality and tone."
    else:
        hint += " Avoid swearing."
    return hint

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

            persona_hint = build_persona_hint(
                sister_name,
                style_hint=f"Expand this 1-line closing in your voice: \"{intro}\" Keep it to 1 short sentence.",
                config=config
            )

            try:
                expansion = await generate_llm_reply(
                    sister=sister_name,
                    user_message=f"{sister_name}: {persona_hint}",
                    theme=None,
                    role="lead",
                    history=[]
                )
                line = expansion if expansion else intro
            except Exception:
                line = intro

            end_msg = f"{sister_name}: {line}"
            await post_to_family(end_msg, sender=sister_name, sisters=sisters, config=config)
            log_event(f"[TASK-END] {sister_name} notified task end.")
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

    persona_hint = build_persona_hint(
        lead,
        style_hint=f"Use this opening as your tone and expand into a 3–5 sentence morning message. \"{intro}\"",
        config=config
    )

    try:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message=f"{lead}: {persona_hint}",
            theme=theme,
            role="lead",
            history=[]
        )
        if not lead_msg:
            lead_msg = intro
    except Exception:
        lead_msg = intro

    today_workout = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{today_workout}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if random.random() < 0.7:
            persona_hint = build_persona_hint(s, "Short supportive morning comment, 1–2 sentences.", config)
            reply = await generate_llm_reply(
                sister=s,
                user_message=f"{s}: {persona_hint}",
                theme=theme,
                role="support",
                history=[]
            )
            if reply:
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    if random.random() < 0.2:
        persona_hint = build_persona_hint(rest, "Quiet short morning remark, 1 sentence.", config)
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message=f"{rest}: {persona_hint}",
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

    persona_hint = build_persona_hint(
        lead,
        style_hint=f"Use this opening as your tone and expand into a 3–5 sentence night message. \"{intro}\"",
        config=config
    )

    try:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message=f"{lead}: {persona_hint}",
            theme=theme,
            role="lead",
            history=[]
        )
        if not lead_msg:
            lead_msg = intro
    except Exception:
        lead_msg = intro

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_workout = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_workout}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if random.random() < 0.6:
            persona_hint = build_persona_hint(s, "Short supportive night comment, 1–2 sentences.", config)
            reply = await generate_llm_reply(
                sister=s,
                user_message=f"{s}: {persona_hint}",
                theme=theme,
                role="support",
                history=[]
            )
            if reply:
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    if random.random() < 0.15:
        persona_hint = build_persona_hint(rest, "Brief quiet night remark, 1 sentence.", config)
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message=f"{rest}: {persona_hint}",
            theme=theme,
            role="rest",
            history=[]
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest, sisters=sisters, config=config)
            append_ritual_log(rest, "rest", theme, rest_reply)

    log_event(f"[SCHEDULER] Night message completed with {lead} as lead")

# ---------------- Spontaneous Tasks ----------------
async def send_spontaneous_task(state, config, sisters):
    """Assign at most one spontaneous task per day across all sisters."""
    today_key = datetime.now().date().isoformat()
    if state.get("spontaneous_task_date") == today_key:
        return  # already assigned today

    chosen = random.choice(config["rotation"])
    sister_name = chosen["name"]

    persona_hint = build_persona_hint(
        sister_name,
        style_hint="Assign a spontaneous discipline or care task in your voice, 1–2 sentences only. Direct and fitting your personality.",
        config=config
    )

    try:
        task_msg = await generate_llm_reply(
            sister=sister_name,
            user_message=f"{sister_name}: {persona_hint}",
            theme=get_current_theme(state, config),
            role="lead",
            history=[]
        )
        if task_msg:
            await post_to_family(f"{sister_name}: {task_msg}", sender=sister_name, sisters=sisters, config=config)
            log_event(f"[SPONTANEOUS] {sister_name} assigned: {task_msg}")
            parse_data_command(sister_name, f"[SPONTANEOUS] {task_msg}")
            state["spontaneous_task_date"] = today_key

            duration_seconds = _extract_duration_seconds(task_msg)
            if duration_seconds:
                cleaned = _remove_duration_phrases(task_msg)
                parse_data_command(sister_name, f"[SPONTANEOUS] {cleaned}")
                await _schedule_spontaneous_end(state, sisters, config, sister_name, duration_seconds)

    except Exception as e:
        log_event(f"[ERROR] Spontaneous task failed for {sister_name}: {e}")
