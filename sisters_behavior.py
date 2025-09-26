import random
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
    return wake <= now <= bed if wake <= bed else now >= wake or now <= bed

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
async def _persona_reply(sname, role, base_prompt, theme, config, history):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Role: {role}. "
        f"{'Swearing allowed.' if allow_swear else 'Do not swear.'} "
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
    lead, supports = rotation["lead"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Good morning.")
    lead_msg = await _persona_reply(
        lead, "lead",
        f"Expand into a warm 3–5 sentence morning greeting. \"{intro}\"",
        theme, config, []
    )

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
                    theme, config, []
                )
                if reply:
                    await post_to_family(reply, sender=s, sisters=sisters, config=config)
                    append_ritual_log(s, "support", theme, reply)

    state["rotation_index"] = state.get("rotation_index", 0) + 1

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, supports = rotation["lead"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Good night.")
    lead_msg = await _persona_reply(
        lead, "lead",
        f"Expand into a thoughtful 3–5 sentence night reflection. \"{intro}\"",
        theme, config, []
    )

    tomorrow = datetime.now().date() + timedelta(days=1)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{get_today_workout(tomorrow)}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if is_awake(next(bot.sister_info for bot in sisters if bot.sister_info["name"] == s), lead):
            if random.random() < 0.6:
                reply = await _persona_reply(
                    s, "support",
                    "Write a short supportive night comment (1–2 sentences).",
                    theme, config, []
                )
                if reply:
                    await post_to_family(reply, sender=s, sisters=sisters, config=config)
                    append_ritual_log(s, "support", theme, reply)

# ---------------- Spontaneous ----------------
async def send_spontaneous_task(state, config, sisters):
    """Trigger a spontaneous chat message with fairness & conversational flavor."""
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    awake = [b.sister_info["name"] for b in sisters if is_awake(b.sister_info, lead)]
    if not awake:
        return

    sister = random.choice(awake)

    # Conversational prompts (with Will nudges, Ivy gets stronger push)
    prompts = [
        "Ask one of your sisters a direct question.",
        "Comment on what Will might be thinking — invite him to respond.",
        "Tease Will playfully to draw him out.",
        "Make a remark that another sibling would want to respond to.",
        "Bring up the current theme and pull someone into the conversation.",
    ]

    if sister == "Ivy":
        # Ivy more likely to nudge Will
        prompts += [
            "Directly tease Will, like a cheeky little sister would.",
            "Ask Will for his opinion, but in a playful or pushy way.",
        ]

    msg = await _persona_reply(
        sister, "support",
        random.choice(prompts),
        theme, config, []
    )
    if msg:
        await post_to_family(msg, sister, sisters, config)
        log_event(f"[SPONTANEOUS] {sister}: {msg}")

# ---------------- Interaction ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    mentions = [s["name"] for s in config["rotation"] if s["name"].lower() in content.lower()]
    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author or not is_awake(bot.sister_info, lead):
            continue

        chance = 0.2
        if sname == lead:
            chance = 0.8
        elif sname in rotation["supports"]:
            chance = 0.5
        elif sname == rotation["rest"]:
            chance = 0.1

        # Mentions or Will-specific triggers
        if sname in mentions or "will" in content.lower():
            chance = 1.0

        # Ivy bias: increase chance if Will is speaking
        if author == "Will" and sname == "Ivy":
            chance = max(chance, 0.9)

        if random.random() < chance:
            reply = await _persona_reply(
                sname, "support",
                f"Reply directly to {author}'s message: \"{content}\". Keep it short and conversational.",
                theme, config, []
            )
            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                log_event(f"[CHAT] {sname} → {author}: {reply}")
