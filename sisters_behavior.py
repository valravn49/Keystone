# sisters_behavior.py
import random
import re
import asyncio
from datetime import datetime, timedelta, time as dtime
from typing import Dict, List, Optional

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# ---------------- Personality tone seeds (for brief on-brand expansions) ----------------
PERSONA_TONES = {
    "Aria": {
        "intro_morning": "Good morning — be gentle with yourself today; remember your duties and care.",
        "intro_night": "Time to rest, sweet one. Reflect kindly on your progress.",
        "closing": "That’s enough time. You can stop now, love.",
    },
    "Selene": {  # motherly
        "intro_morning": "Good morning, darling — take things slowly and be kind to your body today.",
        "intro_night": "Sleep well, my dear. I’ve been thinking of your care and comfort.",
        "closing": "Lovely — your time is up. Come relax and breathe.",
    },
    "Cassandra": {
        "intro_morning": "Morning. Be prepared, stay disciplined, and do not slack.",
        "intro_night": "The day is done. Review your discipline and rest ready for tomorrow.",
        "closing": "Discipline complete. You may end the task — because I allow it.",
    },
    "Ivy": {
        "intro_morning": "Wake up, sleepyhead~ Don’t dawdle or I’ll tease you all day.",
        "intro_night": "Bedtime already? Tuck in, cutie — naughty dreams await.",
        "closing": "Hehe~ done! Bet you squirmed — you can stop now 💕",
    },
}

# ---------------- Basic knobs ----------------
HISTORY_LIMIT = 6
# Channel reply anti-spam is handled in main or earlier versions; here we keep behavior logic.

# Spontaneous task: 1 per day across all sisters
SPONTANEOUS_MAX_PER_DAY = 1

# Casual chatter pacing (seconds)
CHATTER_MIN_SLEEP = 45 * 60
CHATTER_MAX_SLEEP = 110 * 60

# Inline duration parsing for spontaneous tasks (kept private; we never reveal the number)
_DURATION_REGEX = re.compile(r"(\d+)\s*(hours|hour|hrs|hr|h|minutes|minute|mins|min|m)\b", re.I)


# ---------------- Utility: rotation & theme ----------------
def get_today_rotation(state: Dict, config: Dict):
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}


def get_current_theme(state: Dict, config: Dict):
    today = datetime.now().date()
    if state.get("last_theme_update") is None or (
        today.weekday() == 0 and state.get("last_theme_update") != today
    ):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]


async def post_to_family(message: str, sender: Optional[str], sisters, config: Dict):
    """Send to the family channel via the specified sister (or the first ready)."""
    for bot in sisters:
        if bot.is_ready():
            if not sender or bot.sister_info["name"] == sender:
                try:
                    channel = bot.get_channel(config["family_group_channel"])
                    if channel:
                        await channel.send(message)
                        log_event(f"{bot.sister_info['name']} posted: {message}")
                except Exception as e:
                    log_event(f"[ERROR] Failed to send with {bot.sister_info['name']}: {e}")
                break


# ---------------- Scheduling: wake/sleep per sister ----------------
def _pick_hour_in_range(rng: List[int]) -> int:
    lo, hi = int(rng[0]), int(rng[1])
    if hi < lo:
        hi = lo
    return random.randint(lo, hi)


def assign_daily_schedule(state: Dict, config: Dict):
    """Assign (or reuse) today's wake/sleep hour windows from config['schedules']."""
    today = datetime.now().date()
    if state.get("schedules_date") == today and state.get("schedules"):
        return state["schedules"]

    state["schedules"] = {}
    schedules_cfg = config.get("schedules", {})
    rotation = config["rotation"]
    for entry in rotation:
        name = entry["name"]
        scfg = schedules_cfg.get(name, {})
        wake_rng = scfg.get("wake", [7, 9])
        sleep_rng = scfg.get("sleep", [21, 23])
        state["schedules"][name] = {
            "wake": _pick_hour_in_range(wake_rng),
            "sleep": _pick_hour_in_range(sleep_rng),
        }
    state["schedules_date"] = today
    return state["schedules"]


def _hour_in_window(now_hour: int, wake: int, sleep: int) -> bool:
    """Return True if now_hour is within [wake, sleep) in 24h wrap-aware fashion."""
    if wake == sleep:
        return True  # degenerate = always on
    if wake < sleep:
        return wake <= now_hour < sleep
    # wrap past midnight
    return now_hour >= wake or now_hour < sleep


def is_sibling_online(name: str, state: Dict, config: Dict) -> bool:
    """Lead is always online; others respect schedule windows."""
    rotation = get_today_rotation(state, config)
    if name == rotation["lead"]:
        return True
    schedules = assign_daily_schedule(state, config)
    sc = schedules.get(name)
    if not sc:
        return True  # if no schedule, default online
    now_hour = datetime.now().hour
    return _hour_in_window(now_hour, sc["wake"], sc["sleep"])


# ---------------- Inter-sister chatter ----------------
async def inter_sister_replies(state, config, sisters, origin: str, origin_msg: str, theme: str):
    """After a lead/scheduled message, allow sisters to reply once naturally."""
    for s in config["rotation"]:
        name = s["name"]
        if name == origin:
            continue
        if not is_sibling_online(name, state, config):
            continue
        # 40% chance to reply to the origin post
        if random.random() < 0.4:
            await asyncio.sleep(random.randint(15, 75))  # slight delay for realism
            try:
                reply = await generate_llm_reply(
                    sister=name,
                    user_message=f"{origin} said: \"{origin_msg}\". "
                                 f"Write a natural 1–2 sentence reply in {name}'s style.",
                    theme=theme,
                    role="sister",
                    history=[],
                )
                if reply:
                    await post_to_family(reply, sender=name, sisters=sisters, config=config)
                    log_event(f"[INTERACTION] {name} replied to {origin}")
            except Exception as e:
                log_event(f"[ERROR] inter_sister_replies for {name}: {e}")


async def sibling_chatter_loop(state, config, sisters):
    """Runs all day; online siblings may casually ping each other."""
    # Ensure we only start one chatter loop
    if state.get("chatter_task_started"):
        return
    state["chatter_task_started"] = True

    while True:
        theme = get_current_theme(state, config)
        rotation = get_today_rotation(state, config)
        online = [s["name"] for s in config["rotation"] if is_sibling_online(s["name"], state, config)]

        if len(online) >= 2:
            # Attempt a few casual pings per cycle
            attempts = random.randint(1, 2)
            for _ in range(attempts):
                talker = random.choice(online)
                # Don't bias lead every time; anyone can start chatter while online
                targets = [x for x in online if x != talker]
                if not targets:
                    continue
                target = random.choice(targets)
                if random.random() < 0.25:  # 25% chance per attempt
                    try:
                        msg = await generate_llm_reply(
                            sister=talker,
                            user_message=(
                                f"You are {talker}. Send a short, natural 1–2 sentence casual message "
                                f"to {target} in your style. Keep it relevant to daily life or the theme."
                            ),
                            theme=theme,
                            role="sister",
                            history=[],
                        )
                        if msg:
                            await post_to_family(msg, sender=talker, sisters=sisters, config=config)
                            log_event(f"[CHATTER] {talker} pinged {target}")
                    except Exception as e:
                        log_event(f"[ERROR] chatter {talker}->{target}: {e}")

        # Sleep until next light chatter window
        nap = random.randint(CHATTER_MIN_SLEEP, CHATTER_MAX_SLEEP)
        await asyncio.sleep(nap)


def ensure_chatter_loop(state, config, sisters):
    """Helper called by main or startup to ensure continuous chatter."""
    if not state.get("chatter_task_started"):
        asyncio.create_task(sibling_chatter_loop(state, config, sisters))


# ---------------- Rituals (morning/night) ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, supports = rotation["lead"], rotation["supports"]

    # Lead message
    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Good morning.")
    try:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message=f"{lead}: Expand this into a warm 3–5 sentence morning greeting. \"{intro}\"",
            theme=theme,
            role="lead",
            history=[],
        )
        if not lead_msg:
            lead_msg = intro
    except Exception:
        lead_msg = intro

    # Add today's workout (4-day rotation comes from workouts.get_today_workout)
    today_block = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{today_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # A couple of supporters may chime in
    for s in supports:
        if is_sibling_online(s, state, config) and random.random() < 0.7:
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

    # Allow casual inter-sister replies to the lead's post
    asyncio.create_task(inter_sister_replies(state, config, sisters, lead, lead_msg, theme))

    # Advance rotation after morning ritual
    state["rotation_index"] = state.get("rotation_index", 0) + 1


async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, supports = rotation["lead"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Good night.")
    try:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message=f"{lead}: Expand this into a thoughtful 3–5 sentence night reflection. \"{intro}\"",
            theme=theme,
            role="lead",
            history=[],
        )
        if not lead_msg:
            lead_msg = intro
    except Exception:
        lead_msg = intro

    # Add tomorrow's workout
    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Some supporters may add a reflection
    for s in supports:
        if is_sibling_online(s, state, config) and random.random() < 0.6:
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

    # Post-lead replies
    asyncio.create_task(inter_sister_replies(state, config, sisters, lead, lead_msg, theme))


# ---------------- Spontaneous tasks (1 per day, hidden duration end-notice) ----------------
def _extract_duration_seconds(text: str) -> Optional[int]:
    m = _DURATION_REGEX.search(text or "")
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("h"):
        return val * 3600
    return val * 60


async def _notify_end_after(sister_name: str, seconds: int, sisters, config: Dict):
    seed = PERSONA_TONES.get(sister_name, {}).get("closing", "Your task is complete. You may stop now.")
    # Occasionally let LLM rephrase the closing in-voice, still short
    try:
        if random.random() < 0.5:
            alt = await generate_llm_reply(
                sister=sister_name,
                user_message=f"{sister_name}: Rewrite this as a single short line in your voice: \"{seed}\"",
                theme=None,
                role="lead",
                history=[],
            )
            if alt:
                seed = alt.strip()
    except Exception:
        pass

    await asyncio.sleep(max(1, seconds))
    try:
        await post_to_family(f"{sister_name}: {seed}", sender=sister_name, sisters=sisters, config=config)
        log_event(f"[TASK-END] {sister_name} posted end notice (duration hidden).")
    except Exception as e:
        log_event(f"[TASK-END] Error posting end notice: {e}")


async def send_spontaneous_task(state, config, sisters):
    """At most 1 sister-assigned task per day. If none chosen, do nothing."""
    today_key = datetime.now().date().isoformat()
    if state.get("spontaneous_task_day") == today_key:
        return  # already assigned today

    theme = get_current_theme(state, config)
    rotation = get_today_rotation(state, config)
    # Candidate sisters: online at call time
    online_sisters = [s["name"] for s in config["rotation"] if is_sibling_online(s["name"], state, config)]
    if not online_sisters:
        return

    # 30% base chance to assign; you can tune this or gate by config
    if random.random() >= 0.30:
        return

    chooser = random.choice(online_sisters)
    # A few archetypal tasks; can be themed by sister
    archetypes = {
        "Cassandra": [
            "Put your plug in and hold it until I say otherwise.",
            "Do a 20-minute tidy of your space. Quiet and focused.",
            "Posture drill: shoulders down, core on, 15 minutes."
        ],
        "Ivy": [
            "Wear something cute and send a quick check-in selfie (no face needed).",
            "Hold a wall sit and tell me when you break. No fibbing~",
            "Practice your best curtsey in the mirror for a few minutes."
        ],
        "Aria": [
            "Journal three lines about your goals today.",
            "Read for ten unbroken minutes; then share one nice line.",
            "Light stretch break; breathe deeply and unwind."
        ],
        "Selene": [
            "Make tea and drink it slowly while you breathe.",
            "Moisturize and do gentle stretches; tell me how you feel.",
            "Set a calm playlist and tidy one small area."
        ],
    }
    options = archetypes.get(chooser, archetypes["Aria"])
    task_text = random.choice(options)

    # Compose directive
    directive = await generate_llm_reply(
        sister=chooser,
        user_message=(
            f"Write a single short directive in your voice based on this: \"{task_text}\". "
            f"Do NOT include a duration. Be clear and kind if {chooser} is kind; strict if strict."
        ),
        theme=theme,
        role="lead",
        history=[],
    )
    if not directive:
        directive = f"{chooser}: {task_text}"

    await post_to_family(directive, sender=chooser, sisters=sisters, config=config)
    log_event(f"[SPONTANEOUS] {chooser} assigned: {directive}")

    # Mark the day used
    state["spontaneous_task_day"] = today_key

    # Hidden duration end-notice if the *text the user writes later* includes a duration.
    # We also support implicit durations if the archetype implies it; we keep it simple:
    implied_secs = None
    if "posture" in task_text.lower():
        implied_secs = 15 * 60
    elif "read for ten" in task_text.lower():
        implied_secs = 10 * 60
    elif "20-minute tidy" in task_text.lower():
        implied_secs = 20 * 60

    if implied_secs:
        asyncio.create_task(_notify_end_after(chooser, implied_secs, sisters, config))


# ---------------- Message handling (user -> sisters) ----------------
def _add_to_history(state, channel_id, author, content):
    hist = state.setdefault("history", {}).setdefault(channel_id, [])
    hist.append((author, content))
    if len(hist) > HISTORY_LIMIT:
        hist[:] = hist[-HISTORY_LIMIT:]


async def handle_sister_message(state, config, sisters, author: str, content: str, channel_id: int):
    """Main handler used by main.py for inbound messages in the family channel."""
    _add_to_history(state, channel_id, author, content)

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)

    # Weighted pick from recent messages (oldest higher weight) to avoid reply spam to latest only
    history = state["history"].get(channel_id, [])
    if not history:
        return

    # Each bot decides to reply based on role and being online
    for bot in sisters:
        name = bot.sister_info["name"]
        if not is_sibling_online(name, state, config):
            continue

        if name == rotation["lead"]:
            role = "lead"
            should_reply = True
            style_hint = "Reply in 2–4 sentences, guiding the conversation."
        elif name in rotation["supports"]:
            role = "support"
            should_reply = random.random() < 0.6
            style_hint = "Reply in 1–2 sentences, playful or supportive."
        else:
            role = "rest"
            should_reply = random.random() < 0.2
            style_hint = "Reply briefly, 1 short remark."

        if not should_reply:
            continue

        weights = list(range(len(history), 0, -1))  # oldest highest
        pick_author, pick_content = random.choices(history, weights=weights, k=1)[0]

        try:
            reply = await generate_llm_reply(
                sister=name,
                user_message=f"{pick_author}: {pick_content}\n{style_hint}",
                theme=theme,
                role=role,
                history=history,
            )
            if reply:
                await post_to_family(reply, sender=name, sisters=sisters, config=config)
        except Exception as e:
            log_event(f"[ERROR] LLM reply failed for {name}: {e}")
            continue


# ---------------- Public helpers for main ----------------
def ensure_daily_systems(state, config, sisters):
    """Call once at startup to initialize daily schedules & chatter."""
    assign_daily_schedule(state, config)
    ensure_chatter_loop(state, config, sisters)
