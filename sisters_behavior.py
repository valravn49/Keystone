# sisters_behavior.py
import random
import asyncio
import re
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout
from relationships import plot_relationships

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

ALLOWED_NAMES = {"Aria", "Selene", "Cassandra", "Ivy", "Will", "Nick", "Val"}

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
    if sister_info["name"] == lead_name:
        return True
    now = datetime.now().time()
    wake = datetime.strptime(sister_info.get("wake", "06:00"), "%H:%M").time()
    bed = datetime.strptime(sister_info.get("bed", "22:00"), "%H:%M").time()
    if wake <= bed:
        return wake <= now <= bed
    return now >= wake or now <= bed

async def post_to_family(message: str, sender, sisters, config):
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

# ---------------- Cleanup ----------------
def clean_names(text: str) -> str:
    words = text.split()
    fixed = []
    for w in words:
        if w.istitle() and w not in ALLOWED_NAMES:
            fixed.append("Nick")
        else:
            fixed.append(w)
    return " ".join(fixed)

# ---------------- Persona wrapper ----------------
async def _persona_reply(sname, role, base_prompt, theme, history, config, force_workout=False):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    system_reminder = (
        "Only reference siblings by name (Aria, Selene, Cassandra, Ivy, Will) "
        "or the user as Nick or Val. Do not invent new names."
    )

    # Force workout detail if asked
    if force_workout:
        workout_text = get_today_workout()
        base_prompt += f"\nHere is today’s workout plan to include:\n{workout_text}"

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone: {role}. {system_reminder} "
        f"{'Swearing is allowed if it feels natural.' if allow_swear else 'Do not swear.'} "
        f"{base_prompt}"
    )

    reply = await generate_llm_reply(
        sister=sname,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )

    return clean_names(reply or "")

# ---------------- Rituals ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Good morning.")
    lead_msg = await _persona_reply(
        lead, "lead", f"Expand into a warm 3–5 sentence morning greeting. \"{intro}\"", theme, [], config
    )

    workout_block = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    state["rotation_index"] = state.get("rotation_index", 0) + 1

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Good night.")
    lead_msg = await _persona_reply(
        lead, "lead", f"Expand into a thoughtful 3–5 sentence night reflection. \"{intro}\"", theme, [], config
    )

    tomorrow_block = get_today_workout(datetime.now().date() + timedelta(days=1))
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

# ---------------- Spontaneous ----------------
async def send_spontaneous_task(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    awake = [b.sister_info["name"] for b in sisters if is_awake(b.sister_info, lead)]
    if not awake:
        return

    sister = random.choice(awake)
    msg = await _persona_reply(
        sister, "support",
        "Send a casual, natural group chat comment (1–2 sentences). Try to engage someone else.",
        theme, [], config
    )
    if msg:
        await post_to_family(msg, sender=sister, sisters=sisters, config=config)
        log_event(f"[SPONTANEOUS] {sister}: {msg}")

# ---------------- Interaction ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author or not is_awake(bot.sister_info, lead):
            continue

        force_workout = any(word in content.lower() for word in ["exercise", "workout", "train"])

        if sname.lower() in content.lower() or "everyone" in content.lower():
            chance = 1.0
        else:
            chance = 0.2
            if sname == lead: chance = 0.8
            elif sname in rotation["supports"]: chance = 0.5
            elif sname == rotation["rest"]: chance = 0.1

        if random.random() < chance:
            reply = await _persona_reply(
                sname, "support",
                f"Reply directly to {author}'s message: \"{content}\". Keep it short (1–2 sentences).",
                theme, [], config, force_workout=force_workout
            )
            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                log_event(f"[CHAT] {sname} → {author}: {reply}")
