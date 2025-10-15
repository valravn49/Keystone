import random
import asyncio
import datetime
from datetime import timedelta
from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# ---------------------------------------------------------------------------
# Persona tone variations
# ---------------------------------------------------------------------------

PERSONA_TONES = {
    "Aria": {
        "intro_morning": [
            "Morning — I stayed up too late reorganizing notes again.",
            "Good morning. I’m trying to keep it calm today.",
            "Morning, coffee first… then brain.",
        ],
        "intro_night": [
            "Time to rest. I’ll probably read a little before bed.",
            "Good night — today was steady enough.",
            "Lights out soon. Quiet is good.",
        ],
    },
    "Selene": {
        "intro_morning": [
            "Morning, darlings — eat something before you rush off.",
            "Good morning — start slow, breathe.",
            "Morning, loves. Remember water and breakfast.",
        ],
        "intro_night": [
            "Good night, sweet ones. Don’t forget blankets.",
            "Sleep well — be soft with yourselves.",
            "Night night — proud of little things today.",
        ],
    },
    "Cassandra": {
        "intro_morning": [
            "Up. The day won’t wait.",
            "Morning. Let’s keep it tight.",
            "Move. Momentum matters.",
        ],
        "intro_night": [
            "The day’s done. Don’t slack tomorrow.",
            "Turn in. Review and reset.",
            "Done. Sleep on it, wake sharper.",
        ],
    },
    "Ivy": {
        "intro_morning": [
            "Ughhh are we awake? Fine — hi~",
            "Morning, gremlins. No dawdling or I’ll tease.",
            "Good morning~ I call dibs on the mirror.",
        ],
        "intro_night": [
            "Night night! No snoring, I’m serious (I’m not).",
            "Okay bedtime — I’m stealing the fluffy blanket.",
            "Sleep tight~ I’m haunting your dreams.",
        ],
    },
}

# ---------------------------------------------------------------------------
# Shared context for memories and media
# ---------------------------------------------------------------------------

REAL_MEDIA = {
    "games": [
        "The Legend of Zelda: Tears of the Kingdom",
        "Final Fantasy XIV",
        "Hades",
        "Stardew Valley",
        "Elden Ring",
        "Hollow Knight",
        "Zenless Zone Zero",
    ],
    "anime": [
        "Attack on Titan",
        "Demon Slayer",
        "My Hero Academia",
        "Spy x Family",
        "Jujutsu Kaisen",
    ],
    "music": ["lofi hip hop", "Ghibli soundtracks", "synthwave", "indie pop"],
    "shows": ["Arcane", "The Last of Us", "Stranger Things"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_today_rotation(state, config):
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation(state, config):
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])

def get_current_theme(state, config):
    today = datetime.datetime.now().date()
    if state.get("last_theme_update") is None or (
        today.weekday() == 0 and state.get("last_theme_update") != today
    ):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]

def is_awake(sister_info, lead_name, state=None, config=None):
    if sister_info["name"] == lead_name:
        return True
    now = datetime.datetime.now().time()
    wake = datetime.datetime.strptime(sister_info.get("wake", "06:00"), "%H:%M").time()
    bed = datetime.datetime.strptime(sister_info.get("bed", "22:00"), "%H:%M").time()
    if wake <= bed:
        return wake <= now <= bed
    return now >= wake or now <= bed

async def post_to_family(message: str, sender, sisters, config):
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Failed send {sender}: {e}")
            break

# ---------------------------------------------------------------------------
# Persona Reply
# ---------------------------------------------------------------------------

async def _persona_reply(
    sname: str,
    role: str,
    base_prompt: str,
    theme: str,
    history: list,
    config: dict,
    mode: str = "default",
    address_to: str | None = None,
    inject_media: str | None = None,
    project_hint: bool = False,
):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    mode_map = {
        "support": "encouraging, warm, a little teasing",
        "tease": "bratty or playful sibling energy",
        "challenge": "stern but caring sibling tone",
        "story": "short anecdote or personal reflection",
        "default": "casual sibling banter",
    }

    addressing = f"If natural, address {address_to} directly. " if address_to else ""
    media_clause = f"If it fits, mention {inject_media} casually. " if inject_media else ""
    project_clause = "Optionally reference a small update on your personal project. " if project_hint else ""

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone: {role}. Mode: {mode_map.get(mode, 'casual sibling banter')}. "
        f"{'Swearing is fine if natural.' if allow_swear else 'Do not swear.'} "
        f"Talk like real siblings: casual, warm, teasing, familiar. "
        f"{addressing}{media_clause}{project_clause}{base_prompt}"
    )

    return await generate_llm_reply(
        sister=sname,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )

# ---------------------------------------------------------------------------
# Rituals
# ---------------------------------------------------------------------------

async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_morning", ["Morning."]))
    try:
        lead_msg = await _persona_reply(
            lead,
            "lead",
            f'Start from: "{opener}" and expand into 3–5 lines of sibling-like morning chatter.',
            theme,
            [],
            config,
            mode="story",
        )
    except Exception:
        lead_msg = opener

    workout_block = get_today_workout()
    if workout_block:
        lead_msg += f"\n\n🏋️ Today’s workout: {workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)
    advance_rotation(state, config)

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_night", ["Night."]))
    try:
        lead_msg = await _persona_reply(
            lead,
            "lead",
            f'Start from: "{opener}" and expand into 3–5 lines of relaxed sibling reflection.',
            theme,
            [],
            config,
            mode="story",
        )
    except Exception:
        lead_msg = opener

    tomorrow = datetime.datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    if tomorrow_block:
        lead_msg += f"\n\n🌙 Tomorrow’s workout: {tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

# ---------------------------------------------------------------------------
# Spontaneous — conversational & guaranteed engagement
# ---------------------------------------------------------------------------

async def send_spontaneous_task(state, config, sisters):
    now = datetime.datetime.now()
    sc = state.setdefault("shared_context", {})
    last_ts = sc.get("last_spontaneous_ts")

    # Random interval to prevent robotic timing
    if last_ts:
        mins = (now - last_ts).total_seconds() / 60.0
        if mins < random.randint(42, 95):
            return

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    awake = [b.sister_info["name"] for b in sisters if is_awake(b.sister_info, lead, state, config)]
    if not awake:
        return

    # Choose main speaker
    speaker = random.choice(awake)
    targets = [n for n in awake if n != speaker]
    address_to = random.choice(targets) if targets else None

    # Inject occasional real media mention
    media_pool = sum(REAL_MEDIA.values(), [])
    inject_media = random.choice(media_pool) if random.random() < 0.4 else None

    base = "Say something spontaneous to spark conversation between siblings."

    try:
        msg = await _persona_reply(
            speaker, "support", base, theme, [], config,
            mode=random.choice(["tease", "story", "support"]),
            address_to=address_to, inject_media=inject_media, project_hint=True,
        )
    except Exception as e:
        log_event(f"[ERROR] Spontaneous generation failed for {speaker}: {e}")
        return

    if not msg:
        return

    # Post the initiating message
    await post_to_family(msg, sender=speaker, sisters=sisters, config=config)
    log_event(f"[SPONTANEOUS] {speaker}: {msg}")
    state["last_spontaneous_speaker"] = speaker
    sc["last_spontaneous_ts"] = now

    # --- GUARANTEED REPLY SEQUENCE ---
    responders = [n for n in awake if n != speaker]
    if not responders:
        return
    responder = random.choice(responders)
    await asyncio.sleep(random.randint(3, 10))

    try:
        reply = await _persona_reply(
            responder,
            "support",
            f"Respond naturally to {speaker}'s message: \"{msg}\". Keep it conversational and sibling-like.",
            theme,
            [],
            config,
            mode=random.choice(["tease", "support", "story"]),
            address_to=speaker,
        )
        if reply:
            await post_to_family(reply, sender=responder, sisters=sisters, config=config)
            log_event(f"[SPONTANEOUS REPLY] {responder} → {speaker}: {reply}")

            # small chance for a second reply (thread continuation)
            if random.random() < 0.4:
                await asyncio.sleep(random.randint(4, 9))
                follow = await _persona_reply(
                    speaker,
                    "support",
                    f"Continue chatting with {responder} naturally. End the conversation when it feels done.",
                    theme,
                    [],
                    config,
                    mode=random.choice(["tease", "story", "support"]),
                    address_to=responder,
                )
                if follow:
                    await post_to_family(follow, sender=speaker, sisters=sisters, config=config)
                    log_event(f"[FOLLOW-UP] {speaker} → {responder}: {follow}")
    except Exception as e:
        log_event(f"[ERROR] Spontaneous reply sequence failed: {e}")

# ---------------------------------------------------------------------------
# Message Handling — natural back-and-forth
# ---------------------------------------------------------------------------

async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead, state, config):
            continue

        # Name mention guarantees response
        if sname.lower() in content.lower() or "everyone" in content.lower():
            chance = 1.0
        else:
            chance = 0.25
            if sname == lead:
                chance = 0.75
            elif sname in rotation["supports"]:
                chance = 0.45

        if random.random() < chance:
            try:
                reply = await _persona_reply(
                    sname,
                    "support",
                    f"{author} said: \"{content}\". Respond like a sibling — teasing, warm, or amused.",
                    theme,
                    [],
                    config,
                    mode=random.choice(["tease", "support", "story"]),
                    address_to=author,
                )
                if reply:
                    await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                    log_event(f"[CHAT] {sname} → {author}: {reply}")
            except Exception as e:
                log_event(f"[ERROR] Message reply failed for {sname}: {e}")
