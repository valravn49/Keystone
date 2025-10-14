import json
import os
import random
import asyncio
from datetime import datetime, timedelta
from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# ---------------------------------------------------------------------------
# Persona tones
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
# Core helpers
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
    today = datetime.now().date()
    if state.get("last_theme_update") is None or (
        today.weekday() == 0 and state.get("last_theme_update") != today
    ):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]

def is_awake(sister_info, lead_name):
    """Check if awake unless sleeping; lead always awake."""
    if sister_info["name"] == lead_name:
        return True
    now = datetime.now().time()
    wake = datetime.strptime(sister_info.get("wake", "06:00"), "%H:%M").time()
    bed = datetime.strptime(sister_info.get("bed", "22:00"), "%H:%M").time()
    if wake <= bed:
        return wake <= now <= bed
    return now >= wake or now <= bed

async def post_to_family(message: str, sender, sisters, config):
    """Send to family chat via correct bot instance."""
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Send fail {sender}: {e}")
            break

# ---------------------------------------------------------------------------
# Conversation memory helpers
# ---------------------------------------------------------------------------

def _record_conversation(state, speaker, message):
    """Keep rolling short-term history of the chat."""
    hist = state.setdefault("conversation_history", [])
    hist.append({"speaker": speaker, "message": message, "timestamp": datetime.now().isoformat()})
    state["conversation_history"] = hist[-15:]  # keep last 15 turns

def _get_recent_speaker(state):
    hist = state.get("conversation_history", [])
    if hist:
        return hist[-1]["speaker"]
    return None

def _get_recent_messages(state):
    """Return conversation summary for context injection."""
    hist = state.get("conversation_history", [])
    msgs = [f"{h['speaker']}: {h['message']}" for h in hist[-6:]]
    return "\n".join(msgs)

# ---------------------------------------------------------------------------
# Persona wrapper
# ---------------------------------------------------------------------------

async def _persona_reply(sname, role, base_prompt, theme, history, config, mode="default"):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    style = {
        "support": "encouraging but casual",
        "tease": "witty, mischievous sibling energy",
        "challenge": "firm or blunt but caring",
        "story": "tiny anecdote or memory that feels real",
        "default": "natural sibling banter",
    }

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Mode: {style.get(mode, 'default')}. "
        f"Talk like siblings: relaxed, teasing, or warm, not formal. "
        f"{'Swearing is okay if natural.' if allow_swear else 'Do not swear.'} "
        f"{base_prompt}"
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

    intro = random.choice(PERSONA_TONES.get(lead, {}).get("intro_morning", ["Morning."]))
    lead_msg = await _persona_reply(
        lead,
        "lead",
        f"Expand into 3–5 sentences as a warm, realistic morning greeting. Start from: '{intro}'.",
        theme,
        _get_recent_messages(state),
        config,
        mode="story",
    )
    _record_conversation(state, lead, lead_msg)

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

    intro = random.choice(PERSONA_TONES.get(lead, {}).get("intro_night", ["Night."]))
    lead_msg = await _persona_reply(
        lead,
        "lead",
        f"Expand into 3–5 sentences as a reflective good night sibling message. Start from: '{intro}'.",
        theme,
        _get_recent_messages(state),
        config,
        mode="story",
    )
    _record_conversation(state, lead, lead_msg)

    tomorrow = datetime.now().date() + timedelta(days=1)
    workout_block = get_today_workout(tomorrow)
    if workout_block:
        lead_msg += f"\n\n🌙 Tomorrow’s workout: {workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

# ---------------------------------------------------------------------------
# Interaction handler (now with real back-and-forth)
# ---------------------------------------------------------------------------

async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    _record_conversation(state, author, content)
    recent_speaker = _get_recent_speaker(state)

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
            chance = 0.45
        elif sname == rotation["rest"]:
            chance = 0.2

        # Reply more often to whoever just spoke
        if recent_speaker and recent_speaker != sname:
            chance += 0.25
        # Mentioned directly
        if sname.lower() in content.lower():
            chance = 1.0

        if random.random() < min(chance, 1.0):
            mode = random.choice(["tease", "support", "story", "default"])
            reply = await _persona_reply(
                sname,
                "support",
                f"Respond naturally to {author}, continuing the conversation. Be concise (1–2 sentences).",
                theme,
                _get_recent_messages(state),
                config,
                mode=mode,
            )
            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                _record_conversation(state, sname, reply)
                log_event(f"[CHAT] {sname} → {author}: {reply}")

                # Optional: small follow-up back-and-forth
                if random.random() < 0.25:
                    await asyncio.sleep(random.randint(3, 10))
                    follow = await _persona_reply(
                        author,
                        "support",
                        f"Reply casually to {sname}'s last message. End naturally if the topic feels done.",
                        theme,
                        _get_recent_messages(state),
                        config,
                        mode=random.choice(["support", "tease", "default"]),
                    )
                    if follow:
                        await post_to_family(follow, sender=author, sisters=sisters, config=config)
                        _record_conversation(state, author, follow)
                        log_event(f"[FOLLOW-UP] {author} → {sname}: {follow}")
