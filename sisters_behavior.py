import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

from llm import generate_llm_reply
from logger import log_event, append_ritual_log, append_conversation_log
from workouts import get_today_workout
from image_utils import maybe_generate_image_request

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
def get_today_rotation(state: Dict, config: Dict):
    idx = state["rotation_index"] % len(config["rotation"])
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

def is_awake(sister_info, lead_name):
    if sister_info["name"] == lead_name:
        return True
    now = datetime.now().time()
    wake = datetime.strptime(sister_info.get("wake", "06:00"), "%H:%M").time()
    bed = datetime.strptime(sister_info.get("bed", "22:00"), "%H:%M").time()
    if wake <= bed:
        return wake <= now <= bed
    return now >= wake or now <= bed

async def post_to_family(message: str, sender, sisters, config, image=None):
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    if image:
                        await channel.send(message, file=image)
                    else:
                        await channel.send(message)
                    log_event(f"{sender} posted: {message}")
                    append_conversation_log("Sisters", sender, message)
            except Exception as e:
                log_event(f"[ERROR] Failed send {sender}: {e}")
            break

def get_context_history(state: Dict, config: Dict, limit: int = None) -> List[str]:
    """Return last N lines of conversation history for context."""
    lookback = limit or config.get("conversation", {}).get("lookback", 6)
    return state.get("history", {}).get("family", [])[-lookback:]

# ---------------- Persona wrapper ----------------
async def _persona_reply(sname, role, base_prompt, theme, history, config, allow_image=True):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    context = "\n".join(history) if history else ""
    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone: {role}. "
        f"{'Swearing allowed if natural.' if allow_swear else 'Do not swear.'} "
        f"Recent chat context:\n{context}\n\n"
        f"{base_prompt}"
    )

    msg = await generate_llm_reply(
        sister=sname,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )

    # Check if image requested
    if allow_image:
        image = await maybe_generate_image_request(sname, msg, history)
        return msg, image
    return msg, None

# ---------------- Rituals ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Good morning.")
    try:
        lead_msg, image = await _persona_reply(
            lead, "lead",
            f"Expand into a warm 3–5 sentence morning greeting. \"{intro}\"",
            theme, get_context_history(state, config), config
        )
    except Exception:
        lead_msg, image = intro, None

    workout_block = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{workout_block}"

    await post_to_family(lead_msg, lead, sisters, config, image=image)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if is_awake(next(bot.sister_info for bot in sisters if bot.sister_info["name"] == s), lead):
            if random.random() < 0.7:
                reply, image = await _persona_reply(
                    s, "support",
                    "Write a short supportive morning comment (1–2 sentences).",
                    theme, get_context_history(state, config), config
                )
                if reply:
                    await post_to_family(reply, s, sisters, config, image=image)
                    append_ritual_log(s, "support", theme, reply)

    state["rotation_index"] = state.get("rotation_index", 0) + 1

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Good night.")
    try:
        lead_msg, image = await _persona_reply(
            lead, "lead",
            f"Expand into a thoughtful 3–5 sentence night reflection. \"{intro}\"",
            theme, get_context_history(state, config), config
        )
    except Exception:
        lead_msg, image = intro, None

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, lead, sisters, config, image=image)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if is_awake(next(bot.sister_info for bot in sisters if bot.sister_info["name"] == s), lead):
            if random.random() < 0.6:
                reply, image = await _persona_reply(
                    s, "support",
                    "Write a short supportive night comment (1–2 sentences).",
                    theme, get_context_history(state, config), config
                )
                if reply:
                    await post_to_family(reply, s, sisters, config, image=image)
                    append_ritual_log(s, "support", theme, reply)

# ---------------- Spontaneous ----------------
async def send_spontaneous_task(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]
    now = datetime.now()

    cooldowns = state.setdefault("spontaneous_cooldowns", {})
    last_speaker = state.get("last_spontaneous_speaker")

    awake = []
    for bot in sisters:
        sname = bot.sister_info["name"]
        if not is_awake(bot.sister_info, lead):
            continue
        last_time = cooldowns.get(sname)
        if last_time and (now - last_time).total_seconds() < 5400:
            continue
        awake.append(sname)

    if not awake:
        return

    weights = []
    for s in awake:
        base = 1.0
        if s == last_speaker:
            base *= 0.2
        spoken_today = state.setdefault("spontaneous_spoken_today", {})
        if not spoken_today.get(s) or spoken_today[s].date() != now.date():
            base *= 2.0
        weights.append(base)

    sister = random.choices(awake, weights=weights, k=1)[0]

    try:
        msg, image = await _persona_reply(
            sister, "support",
            "Send a casual, natural group chat comment (1–2 sentences).",
            theme, get_context_history(state, config), config
        )
        if msg:
            await post_to_family(msg, sister, sisters, config, image=image)
            log_event(f"[SPONTANEOUS] {sister}: {msg}")
            state["last_spontaneous_speaker"] = sister
            cooldowns[sister] = now
            state.setdefault("spontaneous_spoken_today", {})[sister] = now
    except Exception as e:
        log_event(f"[ERROR] Spontaneous task failed for {sister}: {e}")

# ---------------- Interaction ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    # Track history
    state.setdefault("history", {}).setdefault("family", []).append(f"{author}: {content}")

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead):
            continue

        mentioned = (sname.lower() in content.lower() or "everyone" in content.lower())
        chance = 0.2
        if sname == lead:
            chance = 0.8
        elif sname in rotation["supports"]:
            chance = 0.5
        elif sname == rotation["rest"]:
            chance = 0.1
        if mentioned:
            chance = 1.0

        if random.random() < chance:
            try:
                reply, image = await _persona_reply(
                    sname, "support",
                    f"Reply to {author}'s message: \"{content}\". Keep it natural and engaging.",
                    theme, get_context_history(state, config), config
                )
                if reply:
                    await post_to_family(reply, sname, sisters, config, image=image)
                    log_event(f"[CHAT] {sname} → {author}: {reply}")
            except Exception as e:
                log_event(f"[ERROR] Sister reply failed for {sname}: {e}")
