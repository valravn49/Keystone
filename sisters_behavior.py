import random
import asyncio
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

# Natural progress phrases by range
PROGRESS_PHRASES = {
    "Aria": {
        "early": ["I’ve just opened the first chapter, so to speak.", "Barely started, but it’s a beginning."],
        "mid": ["I’m partway through, it’s slowly shaping up.", "About halfway along, steady and calm."],
        "late": ["Nearly wrapped up — the rest is detail work.", "It’s coming together nicely, almost done."],
        "done": ["I finished it. Quietly satisfying.", "All done — feels neat and complete."]
    },
    "Selene": {
        "early": ["Just starting out, but it feels comforting.", "Barely begun, still early days."],
        "mid": ["It’s coming together, step by step.", "I’m about halfway, and it feels good."],
        "late": ["Most of it is done, just a little left.", "Almost wrapped up, it feels close."],
        "done": ["It’s finished. I’m proud of how it turned out.", "All done — now I can rest easy."]
    },
    "Cassandra": {
        "early": ["I’ve only just started — discipline will get it done.", "Still in the first stage, not good enough yet."],
        "mid": ["Partway through. Progress is steady.", "Halfway there, but I must push harder."],
        "late": ["Almost done, just polishing off the last bit.", "Close to completion — I expect results soon."],
        "done": ["Completed. Efficient and proper.", "Finished — nothing less was acceptable."]
    },
    "Ivy": {
        "early": ["Hehe, I barely touched it~", "Just started, don’t rush me!"],
        "mid": ["Halfway-ish, but I keep getting distracted.", "Partway done, promise I’m working on it~"],
        "late": ["Almost finished~ just a little left to polish.", "It’s sooo close to done!"],
        "done": ["Done! Finally, hehe~", "Wrapped it up — see, I can finish things too!"]
    }
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

# ---------------- Progress helper ----------------
def describe_progress(name: str, progress: float) -> str:
    """Return natural language description of project progress based on personality."""
    if progress >= 1.0:
        return random.choice(PROGRESS_PHRASES[name]["done"])
    elif progress >= 0.7:
        return random.choice(PROGRESS_PHRASES[name]["late"])
    elif progress >= 0.4:
        return random.choice(PROGRESS_PHRASES[name]["mid"])
    else:
        return random.choice(PROGRESS_PHRASES[name]["early"])

# ---------------- Persona wrapper ----------------
async def _persona_reply(sname, role, base_prompt, theme, history, config, project_progress=None):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    # Add project context if available
    progress_phrase = ""
    if project_progress is not None:
        progress_phrase = f" Also mention your project: {describe_progress(sname, project_progress)}"

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone: {role}. "
        f"{'Swearing is allowed if it feels natural.' if allow_swear else 'Do not swear.'} "
        f"{base_prompt}{progress_phrase}"
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
    progress = state.get(f"{lead}_project_progress", random.random())

    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into a warm 3–5 sentence morning greeting. \"{intro}\"",
            theme, [], config, project_progress=progress
        )
    except Exception:
        lead_msg = intro

    workout_block = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if is_awake(next(bot.sister_info for bot in sisters if bot.sister_info["name"] == s), lead):
            if random.random() < 0.7:
                reply = await _persona_reply(
                    s, "support",
                    "Write a short supportive morning comment (1–2 sentences).",
                    theme, [], config
                )
                if reply:
                    await post_to_family(reply, sender=s, sisters=sisters, config=config)
                    append_ritual_log(s, "support", theme, reply)

    state["rotation_index"] = state.get("rotation_index", 0) + 1
