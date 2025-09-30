import os
import re
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# Optional relationships module (safe no-op if missing)
try:
    from relationships import adjust_relationship, plot_relationships
except Exception:
    def adjust_relationship(*args, **kwargs):  # type: ignore
        return None
    def plot_relationships(*args, **kwargs):  # type: ignore
        return None

# ---------- Configurable constants ----------
MAX_CONVO_TURNS = 3            # Max turns in a spontaneous thread
REPLY_WINDOW_SEC = 45          # Spacing between bot replies in a thread
DIRECT_MENTION_FORCE = True    # Always reply when directly mentioned
SUPPORT_REPLY_CHANCE = 0.65    # Supporters' chance to chime in during rituals
REST_REPLY_CHANCE = 0.15       # Resting sister's chance to chime in during rituals
CHANCE_CONTINUE_THREAD = 0.55  # Chance a thread continues to next turn
SPONT_MIN_DELAY = 45 * 60      # 45 min min gap per sister (fairness cooldown)
SPONT_MAX_JITTER = 22 * 60     # add up to ~22 min jitter on task loop
BAD_MOOD_TONE = "short, curt, a bit prickly but not cruel"

# Persona tones for rituals (kept concise; richer tone enforced by persona wrapper)
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
# ---------- Profile parsing / Topic knowledge ----------
PROFILE_PATHS = {
    "Aria": ["/mnt/data/Aria_Full_Profile.txt", "data/Aria_Full_Profile.txt"],
    "Selene": ["/mnt/data/Selene_Full_Profile.txt", "data/Selene_Full_Profile.txt"],
    "Cassandra": ["/mnt/data/Cassandra_Full_Profile.txt", "data/Cassandra_Full_Profile.txt"],
    "Ivy": ["/mnt/data/Ivy_Full_Profile.txt", "data/Ivy_Full_Profile.txt"],
}

def _read_first(paths: List[str]) -> str:
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                continue
    return ""

def _parse_profile_topics(txt: str) -> Dict[str, List[str]]:
    """
    Very lenient parser. Looks for lines like:
      Likes: soulslikes, indie games, skincare
      Dislikes: FPS, horror
      Topics: reading lists, makeup, cardio
    """
    topics = {"likes": [], "dislikes": [], "topics": []}
    for line in txt.splitlines():
        low = line.strip().lower()
        if low.startswith("likes:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            topics["likes"] = vals
        elif low.startswith("dislikes:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            topics["dislikes"] = vals
        elif low.startswith("topics:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            topics["topics"] = vals
    return topics

def _load_topic_knowledge(name: str) -> Dict[str, List[str]]:
    raw = _read_first(PROFILE_PATHS.get(name, []))
    return _parse_profile_topics(raw)

def _stance_for(name: str, content: str) -> str:
    """Return a short stance string based on likes/dislikes of the speaker."""
    tk = _load_topic_knowledge(name)
    text = content.lower()
    like_hit = any(k for k in tk["likes"] if k and k in text)
    dislike_hit = any(k for k in tk["dislikes"] if k and k in text)
    if like_hit and not dislike_hit:
        return "You like this; respond with warmth or enthusiasm (keep it in-character)."
    if dislike_hit and not like_hit:
        return "You're not a fan; be honest but kind (stay in-character)."
    return "Neutral stance; be natural and in-character."

# ---------- Rotation & helpers ----------
def get_today_rotation(state: Dict, config: Dict) -> Dict[str, List[str] | str]:
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation(state: Dict, config: Dict) -> None:
    """Advance rotation once per day when morning ritual fires (idempotent for a day)."""
    today = datetime.now().date()
    if state.get("last_rotation_date") == today:
        return
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])
    state["last_rotation_date"] = today
    log_event(f"[ROTATION] Advanced to index {state['rotation_index']}")

def get_current_theme(state: Dict, config: Dict) -> str:
    today = datetime.now().date()
    if state.get("last_theme_update") is None or (
        today.weekday() == 0 and state.get("last_theme_update") != today
    ):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]

def _normalize_names(content: str) -> str:
    """Replace placeholder names with 'Nick' or 'Val' if present."""
    # Example: some models emit [insert name], <name>, etc.
    content = re.sub(r"\[.*?name.*?\]", "Nick", content, flags=re.I)
    content = content.replace("{name}", "Nick").replace("<name>", "Nick")
    # tiny probabilistic switch to Val to keep variety
    if random.random() < 0.25:
        content = content.replace("Nick", "Val")
    return content

def is_awake(sister_info: Dict, lead_name: str) -> bool:
    """Check if sister is awake unless she’s lead (then always awake)."""
    if sister_info["name"] == lead_name:
        return True
    now = datetime.now().time()
    # Allow config-level schedules (hour ranges) — main maps these to real hours already
    wake_str = sister_info.get("wake", "06:00")
    bed_str = sister_info.get("bed", "22:00")
    wake = datetime.strptime(wake_str, "%H:%M").time()
    bed = datetime.strptime(bed_str, "%H:%M").time()
    if wake <= bed:
        return wake <= now <= bed
    return now >= wake or now <= bed

async def post_to_family(message: str, sender: str, sisters, config: Dict):
    """Send to family channel through the correct bot instance."""
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    final = _normalize_names(message)
                    await channel.send(final)
                    log_event(f"{sender} posted: {final}")
            except Exception as e:
                log_event(f"[ERROR] Failed send {sender}: {e}")
            break

# ---------- Persona wrapper (keeps Aria from going “all books”) ----------
def _anti_bookish_hint(name: str) -> str:
    if name == "Aria":
        return ("Avoid defaulting to book references unless it is directly relevant; "
                "focus on present routines, wellbeing, workouts, and relationships.")
    return ""

def _bad_mood_hint(state: Dict, name: str) -> str:
    mood = state.get("moods", {}).get(name)
    if mood == "bad":
        return f"Today you're in a bad mood; keep replies {BAD_MOOD_TONE}."
    return ""

async def _persona_reply(
    sname: str,
    role: str,
    base_prompt: str,
    theme: Optional[str],
    history: List,
    config: Dict,
    stance_text: Optional[str] = None,
) -> str:
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone role: {role}. "
        f"{'Swearing is allowed if it feels natural.' if allow_swear else 'Do not swear.'} "
        f"{_anti_bookish_hint(sname)} "
        f"{_bad_mood_hint(state=globals().get('state', {}), name=sname)} "
        f"{stance_text or ''} "
        f"{base_prompt}"
    )

    text = await generate_llm_reply(
        sister=sname,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )
    return _normalize_names(text or "")

# ---------- Relationship nudges from Aria’s reflections ----------
def _adjust_from_reflection(state: Dict, speaker: str, text: str, siblings: List[str]) -> None:
    if speaker != "Aria":
        return
    if not callable(adjust_relationship):
        return
    mentioned = [sib for sib in siblings if sib.lower() in text.lower()]
    if not mentioned:
        mentioned = random.sample(siblings, k=min(2, len(siblings)))
    for sib in mentioned:
        if sib == speaker:
            continue
        # crude sentiment hooks
        low = text.lower()
        if any(w in low for w in ["care", "kind", "proud", "support"]):
            adjust_relationship(state, speaker, sib, "affection", +0.08)
        elif any(w in low for w in ["lazy", "slack", "annoy"]):
            adjust_relationship(state, speaker, sib, "conflict", +0.06)
        elif any(w in low for w in ["tease", "playful", "fun"]):
            adjust_relationship(state, speaker, sib, "teasing", +0.07)
        else:
            adjust_relationship(state, speaker, sib, "affection", +0.04)

# ---------- Rituals ----------
async def send_morning_message(state: Dict, config: Dict, sisters):
    # Advance rotation ONLY here (once per calendar day)
    advance_rotation(state, config)

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, supports = rotation["lead"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_morning", "Good morning.")
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into a warm 3–5 sentence morning greeting. \"{intro}\"",
            theme, [], config, stance_text="Stay present-focused and supportive."
        )
    except Exception:
        lead_msg = intro

    workout_block = get_today_workout()
    lead_msg += f"\n\n🏋️ Today’s workout:\n{workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Organic relationship nudge if Aria is lead
    _adjust_from_reflection(state, lead, lead_msg, [s["name"] for s in config["rotation"]])

    # Supporters briefly chime in
    for s in supports:
        if is_awake(next(bot.sister_info for bot in sisters if bot.sister_info["name"] == s), lead):
            if random.random() < SUPPORT_REPLY_CHANCE:
                stance = _stance_for(s, lead_msg)
                reply = await _persona_reply(
                    s, "support",
                    "Write a short supportive morning comment (1–2 sentences).",
                    theme, [], config, stance_text=stance
                )
                if reply:
                    await post_to_family(reply, sender=s, sisters=sisters, config=config)
                    append_ritual_log(s, "support", theme, reply)

    # Optional: daily relationship map (if plotting available)
    try:
        path = plot_relationships(state)
        if path and random.random() < 0.2:  # not every single morning
            await post_to_family(f"(relationship map updated: {os.path.basename(path)})", lead, sisters, config)
    except Exception:
        pass

async def send_night_message(state: Dict, config: Dict, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, supports = rotation["lead"], rotation["supports"]

    intro = PERSONA_TONES.get(lead, {}).get("intro_night", "Good night.")
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f"Expand into a thoughtful 3–5 sentence night reflection. \"{intro}\"",
            theme, [], config, stance_text="Reflect briefly on how the family did today."
        )
    except Exception:
        lead_msg = intro

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    lead_msg += f"\n\n🌙 Tomorrow’s workout:\n{tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    _adjust_from_reflection(state, lead, lead_msg, [s["name"] for s in config["rotation"]])

    for s in supports:
        if is_awake(next(bot.sister_info for bot in sisters if bot.sister_info["name"] == s), lead):
            if random.random() < (SUPPORT_REPLY_CHANCE - 0.05):
                stance = _stance_for(s, lead_msg)
                reply = await _persona_reply(
                    s, "support",
                    "Write a short supportive night comment (1–2 sentences).",
                    theme, [], config, stance_text=stance
                )
                if reply:
                    await post_to_family(reply, sender=s, sisters=sisters, config=config)
                    append_ritual_log(s, "support", theme, reply)

# ---------- Spontaneous conversations (multi-turn, natural ending) ----------
def _cooldown_ok(state: Dict, name: str) -> bool:
    cd = state.setdefault("spontaneous_cooldowns", {})
    last = cd.get(name)
    if not last:
        return True
    return (datetime.now() - last).total_seconds() >= SPONT_MIN_DELAY

def _mark_spoken(state: Dict, name: str) -> None:
    state.setdefault("spontaneous_cooldowns", {})[name] = datetime.now()
    state["last_spontaneous_speaker"] = name
    state.setdefault("spontaneous_spoken_today", {})[name] = datetime.now()

def _pick_starter(state: Dict, sisters, lead_name: str) -> Optional[str]:
    """Pick an awake starter with fairness weighting."""
    awake = []
    for bot in sisters:
        sname = bot.sister_info["name"]
        if not is_awake(bot.sister_info, lead_name):
            continue
        if _cooldown_ok(state, sname):
            awake.append(sname)
    if not awake:
        return None
    weights = []
    last_speaker = state.get("last_spontaneous_speaker")
    today = datetime.now().date()
    spoken_today = state.setdefault("spontaneous_spoken_today", {})
    for s in awake:
        w = 1.0
        if s == last_speaker:
            w *= 0.25
        if not spoken_today.get(s) or spoken_today[s].date() != today:
            w *= 2.0
        if s == lead_name:
            w *= 0.8  # slightly less so lead doesn't dominate
        weights.append(w)
    return random.choices(awake, weights=weights, k=1)[0]

async def _conversation_roundtrip(
    state: Dict, config: Dict, sisters, starter: str, theme: str
):
    """Starter speaks → targeted sibling replies → possible short follow-up (<= MAX_CONVO_TURNS)."""
    all_names = [s["name"] for s in config["rotation"]]
    targets = [n for n in all_names if n != starter]
    target = random.choice(targets)

    # Starter engages someone specifically
    starter_stance = _stance_for(starter, target)
    start_msg = await _persona_reply(
        starter, "support",
        f"Open a friendly, specific 1–2 sentence message directed at {target}. "
        f"Ask a small question or invite comment.",
        theme, [], config, stance_text=starter_stance
    )
    if not start_msg:
        return
    await post_to_family(start_msg, starter, sisters, config)
    _mark_spoken(state, starter)

    # Target replies
    await asyncio.sleep(random.randint(8, REPLY_WINDOW_SEC))
    target_stance = _stance_for(target, start_msg)
    reply1 = await _persona_reply(
        target, "support",
        f"{starter} just said: \"{start_msg}\". Reply naturally in 1–2 sentences. "
        f"Answer any question and add a small follow-up question or remark.",
        theme, [], config, stance_text=target_stance
    )
    if not reply1:
        return
    await post_to_family(reply1, target, sisters, config)
    _mark_spoken(state, target)

    # Optional follow-up (1–2 more turns total)
    turns = 1
    cur_speaker = starter
    other = target
    while turns < MAX_CONVO_TURNS and random.random() < CHANCE_CONTINUE_THREAD:
        await asyncio.sleep(random.randint(8, REPLY_WINDOW_SEC))
        stance = _stance_for(cur_speaker, reply1 if cur_speaker == starter else start_msg)
        follow = await _persona_reply(
            cur_speaker, "support",
            f"Continue the short thread with {other} in 1–2 sentences. "
            f"Be brief; let the exchange wind down naturally.",
            theme, [], config, stance_text=stance
        )
        if not follow:
            break
        await post_to_family(follow, cur_speaker, sisters, config)
        _mark_spoken(state, cur_speaker)
        # swap
        cur_speaker, other = other, cur_speaker
        turns += 1

async def send_spontaneous_task(state: Dict, config: Dict, sisters):
    """Spontaneous chatter that tries to start real conversation with one sibling and can continue briefly."""
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    starter = _pick_starter(state, sisters, lead)
    if not starter:
        return

    # Random jitter so the loop doesn't look exact-hourly
    await asyncio.sleep(random.randint(0, SPONT_MAX_JITTER))

    try:
        await _conversation_roundtrip(state, config, sisters, starter, theme)
    except Exception as e:
        log_event(f"[ERROR] Spontaneous convo failed: {e}")

# ---------- Interaction (message-based) ----------
def _extract_mentions(text: str, names: List[str]) -> List[str]:
    low = text.lower()
    hits = []
    if "@everyone" in low or "everyone" in low:
        return names[:]
    for n in names:
        if n.lower() in low:
            hits.append(n)
    return hits

async def handle_sister_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]
    names = [s["name"] for s in config["rotation"]]

    # Mentions get priority
    mentioned = _extract_mentions(content, names)

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead):
            continue

        force = DIRECT_MENTION_FORCE and (sname in mentioned or "everyone" in content.lower())
        if force:
            chance = 1.0
        else:
            # probabilistic fallback
            chance = 0.22
            if sname == lead:
                chance = 0.75
            elif sname in rotation["supports"]:
                chance = 0.5
            elif sname == rotation["rest"]:
                chance = 0.12

        if random.random() < chance:
            stance = _stance_for(sname, content)
            reply = await _persona_reply(
                sname, "support",
                f"Reply directly to {author}'s message: \"{content}\". Keep it short (1–2 sentences). "
                f"If you know the topic, be specific; otherwise ask a tiny follow-up.",
                theme, [], config, stance_text=stance
            )
            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                log_event(f"[CHAT] {sname} → {author}: {reply}")
