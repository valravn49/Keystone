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


def is_awake(sister_info, lead_name):
    """Check if sister is awake unless she’s lead (then always awake)."""
    if sister_info["name"] == lead_name:
        return True

    now = datetime.now().time()
    wake = datetime.strptime(sister_info.get("wake", "06:00"), "%H:%M").time()
    bed = datetime.strptime(sister_info.get("bed", "22:00"), "%H:%M").time()

    if wake <= bed:
        return wake <= now <= bed
    return now >= wake or now <= bed


async def post_to_family(message: str, sender, sisters, config):
    """Send to family channel through the correct bot instance."""
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"{sender} posted: {message}")
                    # Track participation
                    _track_participation(sender, state)
            except Exception as e:
                log_event(f"[ERROR] Failed send {sender}: {e}")
            break


# ---------------- Participation Tracker ----------------
def _track_participation(sname, state):
    """Track when each sibling last spoke."""
    state.setdefault("last_message_time", {})
    state["last_message_time"][sname] = datetime.now()


def _get_dynamic_weights(awake, state, lead):
    """Return weights adjusted by participation balance."""
    now = datetime.now()
    last_times = state.get("last_message_time", {})

    weights = []
    for s in awake:
        base = 1.0

        # Lead bias
        if s == lead:
            base *= 1.5

        # Silence boost
        last_time = last_times.get(s)
        if last_time:
            silence = (now - last_time).total_seconds() / 3600.0
            base *= (1.0 + min(silence, 6) * 0.2)  # Up to 6h boost
        else:
            base *= 2.0  # Never spoken today

        # Over-participation penalty
        spoken_today = state.setdefault("spoken_today", {})
        if spoken_today.get(s, 0) > 5:
            base *= 0.3

        weights.append(base)

    return weights


# ---------------- Persona wrapper ----------------
async def _persona_reply(sname, role, base_prompt, theme, history, config):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Role: {role}. "
        f"{'Swearing allowed if natural.' if allow_swear else 'Do not swear.'} "
        f"{base_prompt}"
    )

    return await generate_llm_reply(
        sister=sname,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )


# ---------------- Rituals ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Good morning.")
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into a warm 3–5 sentence morning greeting. \"{intro}\"",
            theme, [], config
        )
    except Exception:
        lead_msg = intro

    workout_block = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)
    state["rotation_index"] = state.get("rotation_index", 0) + 1


async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Good night.")
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into a thoughtful 3–5 sentence night reflection. \"{intro}\"",
            theme, [], config
        )
    except Exception:
        lead_msg = intro

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)


# ---------------- Spontaneous ----------------
async def send_spontaneous_task(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]
    now = datetime.now()

    awake = [bot.sister_info["name"] for bot in sisters if is_awake(bot.sister_info, lead)]
    if not awake:
        return

    weights = _get_dynamic_weights(awake, state, lead)
    sister = random.choices(awake, weights=weights, k=1)[0]

    try:
        msg = await _persona_reply(
            sister, "support",
            "Send a casual, conversational group chat comment (1–2 sentences). Reference the last topic or ask a follow-up.",
            theme, [], config
        )
        if msg:
            await post_to_family(msg, sender=sister, sisters=sisters, config=config)
            log_event(f"[SPONTANEOUS] {sister}: {msg}")
            state.setdefault("spoken_today", {})[sister] = state.setdefault("spoken_today", {}).get(sister, 0) + 1
    except Exception as e:
        log_event(f"[ERROR] Spontaneous task failed for {sister}: {e}")


# ---------------- Interaction ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead):
            continue

        # Mentions guarantee a reply
        if sname.lower() in content.lower() or "everyone" in content.lower():
            chance = 1.0
        else:
            chance = 0.2
            if sname == lead:
                chance = 0.8
            elif sname in rotation["supports"]:
                chance = 0.5
            elif sname == rotation["rest"]:
                chance = 0.1

        if random.random() < chance:
            try:
                reply = await _persona_reply(
                    sname, "support",
                    f"Reply directly to {author}'s message: \"{content}\". Be conversational, 1–2 sentences.",
                    theme, [], config
                )
                if reply:
                    await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                    log_event(f"[CHAT] {sname} → {author}: {reply}")
                    state.setdefault("spoken_today", {})[sname] = state.setdefault("spoken_today", {}).get(sname, 0) + 1
            except Exception as e:
                log_event(f"[ERROR] Sister reply failed for {sname}: {e}")
