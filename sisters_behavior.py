import random
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout
from relationships import adjust_relationship, plot_relationships

# Persona tones for ritual starters
PERSONA_TONES = {
    "Aria": {
        "intro_morning": "Good morning — I stayed up too late with my notes again.",
        "intro_night": "Time to rest. I’ll probably read a bit before bed, though.",
    },
    "Selene": {
        "intro_morning": "Morning, darlings — remember to eat something before you rush off.",
        "intro_night": "Good night, sweet ones. Don’t forget your blankets.",
    },
    "Cassandra": {
        "intro_morning": "Up. The day won’t wait for you.",
        "intro_night": "The day’s done. Don’t slack tomorrow.",
    },
    "Ivy": {
        "intro_morning": "Ughhh… do we *have* to be awake? Fine, good morning~",
        "intro_night": "Night night! Don’t let me catch you snoring, hehe.",
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
    """Advance rotation daily so lead changes properly."""
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
    """Check if a sister is awake unless she’s lead (then always awake)."""
    if sister_info["name"] == lead_name:
        return True
    now = datetime.now().time()
    wake = datetime.strptime(sister_info.get("wake", "06:00"), "%H:%M").time()
    bed = datetime.strptime(sister_info.get("bed", "22:00"), "%H:%M").time()
    if wake <= bed:
        return wake <= now <= bed
    return now >= wake or now <= bed

async def post_to_family(message: str, sender, sisters, config):
    """Send a message into the family channel through correct bot instance."""
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
async def _persona_reply(sname, role, base_prompt, theme, history, config, mode="default"):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    # sibling-like interaction styles
    mode_map = {
        "support": "sound encouraging, warm, maybe gentle teasing",
        "tease": "poke fun, sarcastic or bratty sibling energy",
        "challenge": "be blunt, critical, or scolding, like a strict sibling",
        "story": "share a small anecdote or reflection",
        "default": "casual sibling banter, natural back-and-forth",
    }

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone: {role}. Mode: {mode_map.get(mode, 'casual sibling banter')}. "
        f"{'Swearing is fine if natural.' if allow_swear else 'Do not swear.'} "
        f"Talk like siblings do: less formal, sometimes teasing, sometimes supportive. "
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

    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Morning.")
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into 3–5 sentences as a morning sibling greeting. Start from: \"{intro}\"",
            theme, [], config, mode="story"
        )
    except Exception:
        lead_msg = intro

    workout_block = get_today_workout()
    if workout_block:
        lead_msg += f"\n\n🏋️ Today’s workout: {workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Advance rotation after morning lead
    advance_rotation(state, config)

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Night.")
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into 3–5 sentences as a night sibling reflection. Start from: \"{intro}\"",
            theme, [], config, mode="story"
        )
    except Exception:
        lead_msg = intro

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    if tomorrow_block:
        lead_msg += f"\n\n🌙 Tomorrow’s workout: {tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

# ---------------- Spontaneous ----------------
async def send_spontaneous_task(state, config, sisters):
    """Trigger spontaneous sibling chat with fairness & conversation feel."""
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
        if last_time and (now - last_time).total_seconds() < random.randint(3000, 5400):
            continue
        awake.append(sname)

    if not awake:
        return

    # Weighted choice to avoid repeats
    weights = []
    for s in awake:
        base = 1.0
        if s == last_speaker:
            base *= 0.3
        weights.append(base)

    sister = random.choices(awake, weights=weights, k=1)[0]

    # Banter mode bias per sibling
    mode_bias = {
        "Aria": ["story", "support"],
        "Selene": ["support", "story"],
        "Cassandra": ["challenge", "tease"],
        "Ivy": ["tease", "support"],
    }
    mode = random.choice(mode_bias.get(sister, ["default"]))

    try:
        msg = await _persona_reply(
            sister, "support",
            "Say something casual to spark conversation. Address a sibling directly if natural.",
            theme, [], config, mode=mode
        )
        if msg:
            await post_to_family(msg, sender=sister, sisters=sisters, config=config)
            log_event(f"[SPONTANEOUS] {sister}: {msg}")
            state["last_spontaneous_speaker"] = sister
            cooldowns[sister] = now
    except Exception as e:
        log_event(f"[ERROR] Spontaneous task failed for {sister}: {e}")

# ---------------- Interaction ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    # sibling back-and-forth probability
    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead):
            continue

        # If directly mentioned, always reply
        if sname.lower() in content.lower() or "everyone" in content.lower():
            chance = 1.0
        else:
            chance = 0.25
            if sname == lead:
                chance = 0.8
            elif sname in rotation["supports"]:
                chance = 0.5
            elif sname == rotation["rest"]:
                chance = 0.2

        if random.random() < chance:
            try:
                reply = await _persona_reply(
                    sname, "support",
                    f"Reply directly to {author}'s message: \"{content}\". Keep it short and sibling-like — teasing, banter, or casual comment.",
                    theme, [], config, mode=random.choice(["tease","support","challenge","story"])
                )
                if reply:
                    await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                    log_event(f"[CHAT] {sname} → {author}: {reply}")

                    # small chance to continue thread with back-and-forth
                    if random.random() < 0.3:
                        await asyncio.sleep(random.randint(3, 10))
                        follow = await _persona_reply(
                            author, "support",
                            f"Continue the sibling back-and-forth with {sname}. End naturally if it feels done.",
                            theme, [], config
                        )
                        if follow:
                            await post_to_family(follow, sender=author, sisters=sisters, config=config)
                            log_event(f"[CHAT] {author} → {sname}: {follow}")

            except Exception as e:
                log_event(f"[ERROR] Sister reply failed for {sname}: {e}")
