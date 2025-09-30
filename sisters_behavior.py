# sisters_behavior.py
import random
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout
from relationships import plot_relationships

# Persona tones with variations
PERSONA_TONES = {
    "Aria": {
        "intro_morning": [
            "Good morning — be gentle with yourself today; remember your duties and care.",
            "Rise gently — today is another chance to grow with kindness.",
            "Morning, dear one. Keep steady and nurture your responsibilities.",
        ],
        "intro_night": [
            "Time to rest, sweet one. Reflect kindly on your progress.",
            "The day is done — let peace find you tonight.",
            "Rest now, and tomorrow we’ll walk forward together.",
        ],
    },
    "Selene": {
        "intro_morning": [
            "Good morning, darling — take things slowly and be kind to your body today.",
            "Rise softly, love. Let’s treat today with care.",
            "Morning, sweetheart. Ease into today with grace.",
        ],
        "intro_night": [
            "Sleep well, my dear. I’ve been thinking of your care and comfort.",
            "Close your eyes, darling. You’re safe and cherished.",
            "The night embraces you — rest with warmth and calm.",
        ],
    },
    "Cassandra": {
        "intro_morning": [
            "Morning. Be prepared, stay disciplined, and do not slack.",
            "Rise sharp — the day demands order and resolve.",
            "Stand tall this morning. Your discipline will guide you.",
        ],
        "intro_night": [
            "The day is done. Review your discipline and rest ready for tomorrow.",
            "Sleep now, knowing you’ve given what you could.",
            "Night falls — keep your focus ready for the dawn.",
        ],
    },
    "Ivy": {
        "intro_morning": [
            "Wake up, sleepyhead~ Don’t dawdle or I’ll tease you all day.",
            "Mornin’, cutie~ I hope you’re ready for trouble.",
            "Rise and shine, or I’ll pull the covers off you!",
        ],
        "intro_night": [
            "Bedtime already? Tuck in, cutie — naughty dreams await.",
            "The night’s here~ Don’t stay up too late without me.",
            "Sweet dreams~ try not to miss me too much.",
        ],
    },
}

# ---------------- Helpers ----------------
def get_today_rotation(state, config):
    idx = state["rotation_index"] % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation(state, config):
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])

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
            except Exception as e:
                log_event(f"[ERROR] Failed send {sender}: {e}")
            break

# ---------------- Persona wrapper ----------------
async def _persona_reply(sname, role, base_prompt, theme, history, config):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    if sname == "Aria":
        base_prompt += " Avoid always framing thoughts only in terms of books — vary with personal feelings, shared memories, or gentle advice."

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone: {role}. "
        f"{'Swearing is allowed if it feels natural.' if allow_swear else 'Do not swear.'} "
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
    lead = rotation["lead"]

    intro_options = PERSONA_TONES.get(lead, {}).get("intro_morning", ["Good morning."])
    intro = random.choice(intro_options)
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

    advance_rotation(state, config)

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    intro_options = PERSONA_TONES.get(lead, {}).get("intro_night", ["Good night."])
    intro = random.choice(intro_options)
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
    """Trigger a spontaneous chat message with fairness & cooldowns, with conversation chaining."""
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
        if last_time and (now - last_time).total_seconds() < 3600:
            continue
        awake.append(sname)

    if not awake:
        return

    sister = random.choice(awake)

    try:
        msg = await _persona_reply(
            sister, "support",
            "Send a casual, natural group chat comment (1–2 sentences). Try to engage someone else.",
            theme, [], config
        )
        if msg:
            await post_to_family(msg, sender=sister, sisters=sisters, config=config)
            log_event(f"[SPONTANEOUS] {sister}: {msg}")
            state["last_spontaneous_speaker"] = sister
            cooldowns[sister] = now
            state.setdefault("spontaneous_spoken_today", {})[sister] = now

            # Start a conversation chain
            await _maybe_continue_conversation(state, config, sisters, sister, msg, theme)

    except Exception as e:
        log_event(f"[ERROR] Spontaneous task failed for {sister}: {e}")

# ---------------- Conversation chaining ----------------
async def _maybe_continue_conversation(state, config, sisters, starter, starter_msg, theme, depth=0):
    if depth > 3:
        return
    chance = 0.6 - (depth * 0.2)
    if random.random() > chance:
        return

    possible_repliers = [s["name"] for s in config["rotation"] if s["name"] != starter]
    replier = random.choice(possible_repliers)

    try:
        reply = await _persona_reply(
            replier, "support",
            f"Reply naturally to {starter}'s message: \"{starter_msg}\" in 1–2 sentences. Make it feel conversational.",
            theme, [], config
        )
        if reply:
            await post_to_family(reply, sender=replier, sisters=sisters, config=config)
            log_event(f"[CHAIN] {replier} → {starter}: {reply}")
            await _maybe_continue_conversation(state, config, sisters, replier, reply, theme, depth+1)
    except Exception as e:
        log_event(f"[ERROR] Conversation chain failed: {e}")

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

        if sname.lower() in content.lower() or "everyone" in content.lower():
            chance = 1.0
        else:
            chance = 0.3 if sname in rotation["supports"] else 0.15

        if random.random() < chance:
            try:
                reply = await _persona_reply(
                    sname, "support",
                    f"Reply directly to {author}'s message: \"{content}\". Keep it short (1–2 sentences).",
                    theme, [], config
                )
                if reply:
                    await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                    log_event(f"[CHAT] {sname} → {author}: {reply}")
                    await _maybe_continue_conversation(state, config, sisters, sname, reply, theme)
            except Exception as e:
                log_event(f"[ERROR] Sister reply failed for {sname}: {e}")
