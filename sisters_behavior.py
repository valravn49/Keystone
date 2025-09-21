# sisters_behavior.py
import random
import re
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# ---------------- Persona tones ----------------
PERSONA_TONES = {
    "Aria": {
        "intro_morning": "Good morning — be gentle with yourself today; remember your duties and care.",
        "intro_night": "Time to rest, sweet one. Reflect kindly on your progress.",
        "end_line": "That’s enough time. You can stop now, love."
    },
    "Selene": {
        "intro_morning": "Good morning, darling — take things slowly and be kind to your body today.",
        "intro_night": "Sleep well, my dear. I’ve been thinking of your care and comfort.",
        "end_line": "Lovely — your time is up. Come relax and breathe."
    },
    "Cassandra": {
        "intro_morning": "Morning. Be prepared, stay disciplined, and do not slack.",
        "intro_night": "The day is done. Review your discipline and rest ready for tomorrow.",
        "end_line": "Discipline complete. You may end the task — because I allow it."
    },
    "Ivy": {
        "intro_morning": "Wake up, sleepyhead~ Don’t dawdle or I’ll tease you all day.",
        "intro_night": "Bedtime already? Tuck in, cutie — naughty dreams await.",
        "end_line": "Hehe~ done! You can stop now 💕"
    },
}

# ---------------- Message parsing helpers ----------------
HISTORY_LIMIT = 6
_DURATION_REGEX = re.compile(r"(\d+)\s*(hours|hour|hrs|hr|h|minutes|minute|mins|min|m)\b", re.I)

def _extract_duration_seconds(text: str):
    """Return duration in seconds if present; otherwise None."""
    if not text:
        return None
    m = _DURATION_REGEX.search(text)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2).lower()
    return val * 3600 if unit.startswith("h") else val * 60

def _strip_leading_name_prefix(sister_name: str, text: str) -> str:
    """
    Prevent outputs like 'aria:' at the start if the LLM mirrors a name.
    Remove only a leading '<name>:' once; preserve the rest.
    """
    if not text:
        return text
    lowered = text.strip().lower()
    prefix = f"{sister_name.lower()}:"
    if lowered.startswith(prefix):
        parts = text.split(":", 1)
        return parts[1].lstrip() if len(parts) > 1 else text
    return text

# ---------------- Shared helpers ----------------
def add_to_history(state, channel_id, author, content):
    if channel_id not in state["history"]:
        state["history"][channel_id] = []
    state["history"][channel_id].append((author, content))
    if len(state["history"][channel_id]) > HISTORY_LIMIT:
        state["history"][channel_id] = state["history"][channel_id][-HISTORY_LIMIT:]

def get_today_rotation(state, config):
    idx = state.get("rotation_index", 0) % len(config["rotation"])
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
    """Lead sister posts a morning message at 06:00 with today’s full workout."""
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
        lead_msg = _strip_leading_name_prefix(lead, lead_msg)
    except Exception:
        lead_msg = intro

    # Add today’s workout block (formatted by workouts.py)
    workout_block = get_today_workout()
    lead_msg = f"{lead_msg}\n\n🏋️ Today’s workout:\n{workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Optional supporters
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
                reply = _strip_leading_name_prefix(s, reply)
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    # Advance who’s lead/rest
    state["rotation_index"] = state.get("rotation_index", 0) + 1
    log_event(f"[SCHEDULER] Morning message completed with {lead} as lead")

async def send_night_message(state, config, sisters):
    """Lead sister posts a night message at 22:00 with tomorrow’s workout preview."""
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
        lead_msg = _strip_leading_name_prefix(lead, lead_msg)
    except Exception:
        lead_msg = intro

    # Add tomorrow’s workout block
    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    lead_msg = f"{lead_msg}\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

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
                reply = _strip_leading_name_prefix(s, reply)
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    log_event(f"[SCHEDULER] Night message completed with {lead} as lead")

# ---------------- Spontaneous tasks ----------------
def _spontaneous_ok_today(state) -> bool:
    """Enforce 1+1 rule: max one task per day and not on consecutive days."""
    today = datetime.now().date()
    last = state.get("last_spontaneous_task")  # iso date string or None
    if last is None:
        return True
    try:
        last_date = datetime.fromisoformat(last).date()
    except Exception:
        try:
            last_date = datetime.strptime(last, "%Y-%m-%d").date()
        except Exception:
            return True
    if last_date == today:
        return False  # already assigned today
    if last_date == (today - timedelta(days=1)):
        return False  # consecutive-day block
    return True

async def _notify_task_end(state, sisters, config, sister_name: str, duration_seconds: int):
    """Wait duration and post a single end notice in sister’s voice, without revealing duration."""
    async def _runner():
        try:
            await asyncio.sleep(duration_seconds)
            end_line = PERSONA_TONES.get(sister_name, {}).get("end_line", "Your task is complete. You may stop now.")
            try:
                stylized = await generate_llm_reply(
                    sister=sister_name,
                    user_message=f"{sister_name}: Rewrite this as one short sentence in your voice, do not mention time: \"{end_line}\"",
                    theme=None,
                    role="lead",
                    history=[],
                )
                if stylized:
                    end_line = _strip_leading_name_prefix(sister_name, stylized)
            except Exception:
                pass
            await post_to_family(end_line, sender=sister_name, sisters=sisters, config=config)
            log_event(f"[TASK-END] {sister_name} posted end-of-task notice.")
        except asyncio.CancelledError:
            log_event("[TASK-END] End notice cancelled.")
        except Exception as e:
            log_event(f"[TASK-END] Error: {e}")

    key = f"{datetime.now().date().isoformat()}_{sister_name}"
    task = asyncio.create_task(_runner())
    state.setdefault("spontaneous_end_tasks", {})[key] = task

async def send_spontaneous_task(state, config, sisters):
    """
    Try to assign one spontaneous task now (if allowed).
    The lead sister for the current rotation assigns; duration (if detected) triggers an end notice.
    """
    spont_cfg = config.get("spontaneous_chat", {})
    if not spont_cfg.get("enabled", True):
        return
    if not _spontaneous_ok_today(state):
        return

    # Chance to assign when the loop wakes up
    base_chance = float(spont_cfg.get("reply_chance", 0.35))
    if random.random() > base_chance:
        return

    rotation = get_today_rotation(state, config)
    lead = rotation["lead"]
    theme = get_current_theme(state, config)

    prompt = (
        f"{lead}: Propose a single-sentence task to assign right now. "
        f"Do not state an exact duration. Keep it clear, actionable, matching your persona. "
        f"Categories may include posture, light discipline, service, or training."
    )
    try:
        task_line = await generate_llm_reply(
            sister=lead,
            user_message=prompt,
            theme=theme,
            role="lead",
            history=[],
        )
        task_line = _strip_leading_name_prefix(lead, task_line)
    except Exception as e:
        log_event(f"[SPONT] LLM error: {e}")
        return

    await post_to_family(task_line, sender=lead, sisters=sisters, config=config)
    log_event(f"[SPONT] {lead} assigned: {task_line}")

    # Record today as having assigned a spontaneous task (1+1 rule)
    state["last_spontaneous_task"] = datetime.now().date().isoformat()
    state["last_spontaneous_sister"] = lead

    # If a duration phrase slipped in, schedule an end notice (without revealing duration)
    seconds = _extract_duration_seconds(task_line)
    if seconds and seconds > 0:
        await _notify_task_end(state, sisters, config, lead, seconds)

# ---------------- Chat handler ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    """
    Called from main.py on every user message in the family channel.
    Basic lead/support/rest selection with minimal throttling (rotation logic is handled elsewhere).
    """
    add_to_history(state, channel_id, author, content)

    rotation = get_today_rotation(state, config)
    name_choices = [rotation["lead"]] + rotation["supports"] + [rotation["rest"]]
    weights = [0.9] + [0.5] * len(rotation["supports"]) + [0.15]
    sister_name = random.choices(name_choices, weights=weights, k=1)[0]

    style_hint = (
        "Reply in 2–4 sentences, guiding the conversation."
        if sister_name == rotation["lead"]
        else ("Reply in 1–2 sentences, playful or supportive."
              if sister_name in rotation["supports"]
              else "Reply briefly, 1 short remark.")
    )

    history = state["history"].get(channel_id, [])
    short_context = "\n".join(f"{a}: {c}" for a, c in history[-3:])

    try:
        reply = await generate_llm_reply(
            sister=sister_name,
            user_message=f"Most recent message from {author}: \"{content}\"\nContext:\n{short_context}\n{style_hint}",
            theme=get_current_theme(state, config),
            role="support" if sister_name != rotation["lead"] else "lead",
            history=history[-HISTORY_LIMIT:],
        )
    except Exception as e:
        log_event(f"[CHAT] LLM error for {sister_name}: {e}")
        return

    if reply:
        reply = _strip_leading_name_prefix(sister_name, reply)
        await post_to_family(reply, sender=sister_name, sisters=sisters, config=config)
        append_ritual_log(sister_name, "chat", get_current_theme(state, config), reply)

# ---------------- Daily scheduler (fixed times) ----------------
async def scheduler_loop(state, config, sisters):
    """
    Fires morning at 06:00 and night at 22:00 every day.
    Uses a simple sleep-until-next-target approach to avoid drift.
    """
    SCHEDULE = [(6, 0, send_morning_message), (22, 0, send_night_message)]
    while True:
        now = datetime.now()
        waits = []
        for hour, minute, func in SCHEDULE:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            waits.append((target - now, func, hour, minute))
        delta, func, hour, minute = min(waits, key=lambda t: t[0])
        sleep_s = max(1, int(delta.total_seconds()))
        log_event(f"[SCHEDULER] Sleeping ~{sleep_s}s until {hour:02d}:{minute:02d} for {func.__name__}")
        await asyncio.sleep(sleep_s)
        try:
            await func(state, config, sisters)
        except Exception as e:
            log_event(f"[SCHEDULER] Error in scheduled task {func.__name__}: {e}")

# ---------------- Spontaneous loop (random intervals) ----------------
async def spontaneous_loop(state, config, sisters):
    """
    Wakes at random intervals during the day and attempts to assign at most ONE spontaneous task per day,
    honoring the 1+1 rule (no consecutive days). Interval bounds come from config.spontaneous_chat.
    """
    spont_cfg = config.get("spontaneous_chat", {})
    if not spont_cfg.get("enabled", True):
        log_event("[SPONT] spontaneous_chat disabled.")
        return

    min_minutes = int(spont_cfg.get("min_minutes", 45))
    max_minutes = int(spont_cfg.get("max_minutes", 90))
    if max_minutes < min_minutes:
        max_minutes = min_minutes

    while True:
        # Pick a random sleep in the configured window
        wait_min = random.randint(min_minutes, max_minutes)
        log_event(f"[SPONT] Sleeping ~{wait_min} minutes until next attempt.")
        await asyncio.sleep(wait_min * 60)

        # Try to assign (1+1 rule and chance handled inside)
        try:
            await send_spontaneous_task(state, config, sisters)
        except Exception as e:
            log_event(f"[SPONT] Error in send_spontaneous_task: {e}")
