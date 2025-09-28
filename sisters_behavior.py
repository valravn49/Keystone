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
            except Exception as e:
                log_event(f"[ERROR] Failed send {sender}: {e}")
            break

# ---------------- Relationship System ----------------
def init_relationships(state, config):
    if "relationships" not in state:
        state["relationships"] = {}
        names = [s["name"] for s in config["rotation"]]
        for a in names:
            for b in names:
                if a != b:
                    state["relationships"][f"{a}→{b}"] = {
                        "affection": 0.5,
                        "teasing": 0.5,
                        "conflict": 0.2,
                    }

def adjust_relationship(state, a, b, affection=0, teasing=0, conflict=0):
    key = f"{a}→{b}"
    if key in state["relationships"]:
        rel = state["relationships"][key]
        rel["affection"] = max(0.0, min(1.0, rel["affection"] + affection))
        rel["teasing"] = max(0.0, min(1.0, rel["teasing"] + teasing))
        rel["conflict"] = max(0.0, min(1.0, rel["conflict"] + conflict))

def evolve_relationships(state, config):
    """Daily drift toward core personality baselines."""
    names = [s["name"] for s in config["rotation"]]
    for a in names:
        for b in names:
            if a == b:
                continue
            rel = state["relationships"].get(f"{a}→{b}")
            if not rel:
                continue

            # Personality-driven drift
            if a == "Aria":
                rel["affection"] = min(1.0, rel["affection"] + 0.01)
            if a == "Selene":
                rel["affection"] = min(1.0, rel["affection"] + 0.015)
            if a == "Cassandra":
                rel["conflict"] = min(1.0, rel["conflict"] + 0.01)
            if a == "Ivy":
                rel["teasing"] = min(1.0, rel["teasing"] + 0.02)
            if a == "Will":
                rel["affection"] = max(0.0, rel["affection"] - 0.005)

# ---------------- Persona wrapper ----------------
async def _persona_reply(sname, role, base_prompt, theme, history, config, target=None, state=None):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    rel_context = ""
    if target and state and f"{sname}→{target}" in state["relationships"]:
        rel = state["relationships"][f"{sname}→{target}"]
        if rel["affection"] > rel["teasing"] and rel["affection"] > rel["conflict"]:
            rel_context = "Respond warmly, supportive, caring."
        elif rel["teasing"] >= rel["affection"] and rel["teasing"] > rel["conflict"]:
            rel_context = "Respond playfully, teasingly."
        elif rel["conflict"] > 0.5:
            rel_context = "Respond bluntly, possibly critical."

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone: {role}. "
        f"{'Swearing is allowed if it feels natural.' if allow_swear else 'Do not swear.'} "
        f"{rel_context} "
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
    init_relationships(state, config)
    evolve_relationships(state, config)

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Good morning.")
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into a warm 3–5 sentence morning greeting. \"{intro}\"",
            theme, [], config, state=state
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
                    theme, [], config, target=lead, state=state
                )
                if reply:
                    await post_to_family(reply, sender=s, sisters=sisters, config=config)
                    append_ritual_log(s, "support", theme, reply)
                    adjust_relationship(state, s, lead, affection=0.05)

    state["rotation_index"] = state.get("rotation_index", 0) + 1

async def send_night_message(state, config, sisters):
    init_relationships(state, config)
    evolve_relationships(state, config)

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Good night.")
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into a thoughtful 3–5 sentence night reflection. \"{intro}\"",
            theme, [], config, state=state
        )
    except Exception:
        lead_msg = intro

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if is_awake(next(bot.sister_info for bot in sisters if bot.sister_info["name"] == s), lead):
            if random.random() < 0.6:
                reply = await _persona_reply(
                    s, "support",
                    "Write a short supportive night comment (1–2 sentences).",
                    theme, [], config, target=lead, state=state
                )
                if reply:
                    await post_to_family(reply, sender=s, sisters=sisters, config=config)
                    append_ritual_log(s, "support", theme, reply)
                    adjust_relationship(state, s, lead, affection=0.05)

# ---------------- Spontaneous ----------------
async def send_spontaneous_task(state, config, sisters):
    """Trigger a conversational spontaneous chat message."""
    init_relationships(state, config)

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

    sister = random.choice(awake)
    target = random.choice([n for n in awake if n != sister]) if len(awake) > 1 else None

    try:
        msg = await _persona_reply(
            sister, "support",
            f"Start a short conversational comment{' directed at ' + target if target else ''}.",
            theme, [], config, target=target, state=state
        )
        if msg:
            await post_to_family(msg, sender=sister, sisters=sisters, config=config)
            log_event(f"[SPONTANEOUS] {sister}: {msg}")
            state["last_spontaneous_speaker"] = sister
            cooldowns[sister] = now
            if target:
                adjust_relationship(state, sister, target, affection=0.02, teasing=0.01)
    except Exception as e:
        log_event(f"[ERROR] Spontaneous task failed for {sister}: {e}")

# ---------------- Interaction ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    init_relationships(state, config)
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead):
            continue

        chance = 0.25
        if sname == lead:
            chance = 0.7
        elif sname in rotation["supports"]:
            chance = 0.5
        elif sname == rotation["rest"]:
            chance = 0.15

        mentioned = sname.lower() in content.lower() or "everyone" in content.lower()
        if mentioned:
            chance = 1.0

        if random.random() < chance:
            try:
                reply = await _persona_reply(
                    sname, "support",
                    f"Reply to {author}'s message: \"{content}\". Keep it short (1–2 sentences).",
                    theme, [], config, target=author, state=state
                )
                if reply:
                    await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                    log_event(f"[CHAT] {sname} → {author}: {reply}")
                    adjust_relationship(state, sname, author, affection=0.02)
            except Exception as e:
                log_event(f"[ERROR] Sister reply failed for {sname}: {e}")
