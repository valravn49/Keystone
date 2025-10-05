import json
import os
import random
import asyncio
from datetime import datetime, timedelta, time

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# ---------------------------------------------------------------------------
# Personality tones for ritual OPENERS only (we'll add variety in prompts).
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
# Helpers: profiles, memory, scheduling, awake checks
# ---------------------------------------------------------------------------

def _profile_path(name: str) -> str:
    # Personality JSON optional
    # Fallback defaults are inside code if file is missing.
    return f"/mnt/data/{name}_Personality.json"

def _memory_path(name: str) -> str:
    # Long-lived memory JSON optional
    return f"/mnt/data/{name}_Memory.json"

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Failed reading {path}: {e}")
    return default

def load_persona(name: str) -> dict:
    # Minimal defaults if no JSON present
    defaults = {
        "name": name,
        "likes": [],
        "dislikes": [],
        "speech_examples": [],
        "core_personality": "",
    }
    data = _load_json(_profile_path(name), defaults)
    # Normalize fields
    data.setdefault("likes", [])
    data.setdefault("dislikes", [])
    data.setdefault("speech_examples", [])
    data.setdefault("core_personality", "")
    return data

def load_memory(name: str) -> dict:
    defaults = {"projects": {}, "recent_notes": []}
    data = _load_json(_memory_path(name), defaults)
    data.setdefault("projects", {})
    data.setdefault("recent_notes", [])
    return data

def save_memory(name: str, memo: dict) -> None:
    try:
        path = _memory_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memo, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Failed writing memory for {name}: {e}")

def _assign_today_schedule(name: str, state: dict, config: dict):
    # Uses config["schedules"][Name] = {"wake":[lo,hi],"sleep":[lo,hi]}
    key = f"{name}_schedule"
    kd = f"{key}_date"
    today = datetime.now().date()
    if state.get(kd) == today and key in state:
        return state[key]

    sch = (config.get("schedules", {}) or {}).get(name, {"wake": [6, 8], "sleep": [22, 23]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        return random.randint(lo, hi) if hi >= lo else lo

    schedule = {"wake": pick(sch.get("wake", [6, 8])), "sleep": pick(sch.get("sleep", [22, 23]))}
    state[key] = schedule
    state[kd] = today
    return schedule

def _now_time() -> time:
    return datetime.now().time()

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    # Inclusively awake window; handles overnight wrap.
    if wake == sleep:
        return True
    if wake < sleep:
        return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_awake(sister_info, lead_name, state=None, config=None):
    """Awake unless sleeping window; lead is always 'awake' for rituals."""
    if sister_info["name"] == lead_name:
        return True
    if state is None or config is None:
        # Legacy behavior (fixed window)
        now = _now_time()
        wake = datetime.strptime(sister_info.get("wake", "06:00"), "%H:%M").time()
        bed = datetime.strptime(sister_info.get("bed", "22:00"), "%H:%M").time()
        if wake <= bed:
            return wake <= now <= bed
        return now >= wake or now <= bed
    # Config schedule version
    sc = _assign_today_schedule(sister_info["name"], state, config)
    now_h = datetime.now().hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

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
    # Weekly theme advance on Mondays or first run
    if state.get("last_theme_update") is None or (today.weekday() == 0 and state.get("last_theme_update") != today):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]

async def post_to_family(message: str, sender, sisters, config):
    """Send into family channel through correct bot instance."""
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
# Shared context helpers: media, memories, projects
# ---------------------------------------------------------------------------

REAL_MEDIA = {
    # A small curated pool that "feels real" and is safe; siblings will react if in likes/dislikes.
    "games": [
        "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
        "Stardew Valley", "Elden Ring", "Hollow Knight", "Overwatch 2"
    ],
    "anime": [
        "Attack on Titan", "Demon Slayer", "Jujutsu Kaisen", "My Hero Academia", "Spy x Family"
    ],
    "music": [
        "lofi hip hop", "indie pop playlists", "Ghibli soundtracks", "synthwave",
    ],
    "shows": [
        "The Mandalorian", "Arcane", "The Last of Us", "Stranger Things"
    ]
}

def _ensure_shared_context(state: dict):
    sc = state.setdefault("shared_context", {})
    sc.setdefault("memories", [])       # list of small strings describing plausible moments
    sc.setdefault("projects", {})       # {name: {"title": str, "progress": float, "note": str}}
    sc.setdefault("last_media_mentions", [])  # rolling recent media mentions
    sc.setdefault("last_spontaneous_ts", None)
    sc.setdefault("convo_threads", {})  # {channel_id: {"last_author":..., "turns": int}}
    return sc

def _record_memory(state: dict, text: str):
    sc = _ensure_shared_context(state)
    sc["memories"] = (sc.get("memories", []) + [text])[-50:]  # cap

def _maybe_seed_project(state: dict, name: str):
    sc = _ensure_shared_context(state)
    if name not in sc["projects"]:
        # Seed a simple individualized project to start threads
        seeds = {
            "Aria": {"title": "Weekly planner revamp", "progress": round(random.uniform(0.2, 0.6), 2), "note": "color tabs and layouts"},
            "Selene": {"title": "Comfort-food recipe cards", "progress": round(random.uniform(0.3, 0.7), 2), "note": "handwritten set"},
            "Cassandra": {"title": "Shelf re-organization", "progress": round(random.uniform(0.5, 0.9), 2), "note": "labeling lower drawers"},
            "Ivy": {"title": "Closet restyle challenge", "progress": round(random.uniform(0.1, 0.5), 2), "note": "mismatch fits on purpose"},
        }
        sc["projects"][name] = seeds.get(name, {"title": "Small personal task", "progress": 0.3, "note": "low-key"})

def _update_project(state: dict, name: str, small_step: bool = True):
    sc = _ensure_shared_context(state)
    _maybe_seed_project(state, name)
    pj = sc["projects"].get(name)
    if not pj:
        return
    delta = random.uniform(0.02, 0.08) if small_step else random.uniform(0.08, 0.18)
    pj["progress"] = max(0.0, min(1.0, round(pj["progress"] + delta, 2)))

def _media_from_text(text: str) -> list:
    hits = []
    lower = text.lower()
    for cat, items in REAL_MEDIA.items():
        for it in items:
            if it.lower() in lower:
                hits.append(it)
    return list(set(hits))

def _media_reaction_weight(name: str, text: str, config: dict) -> float:
    persona = load_persona(name)
    likes = " ".join(persona.get("likes", [])).lower()
    dislikes = " ".join(persona.get("dislikes", [])).lower()
    # If any known media matches likes, boost; if matches dislikes, reduce
    found = _media_from_text(text)
    boost = 0.0
    for m in found:
        if any(w in likes for w in m.lower().split()):
            boost += 0.25
        if any(w in dislikes for w in m.lower().split()):
            boost -= 0.2
    return boost

# ---------------------------------------------------------------------------
# Persona wrapper with sibling vibe (and anti-“book only” bias for Aria)
# ---------------------------------------------------------------------------

async def _persona_reply(
    sname: str,
    role: str,
    base_prompt: str,
    theme: str,
    history: list,
    config: dict,
    mode: str = "default",
    avoid_books_if_aria: bool = True,
    address_to: str | None = None,
    inject_media: str | None = None,
    project_hint: bool = False,
):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    # Lightweight style modes for banter:
    mode_map = {
        "support": "encouraging, warm, a little teasing if natural",
        "tease": "poke fun, playful or bratty sibling energy (keep it kind)",
        "challenge": "blunt or scolding like a strict sibling, but not cruel",
        "story": "share a tiny anecdote or reflection about a real-feeling moment",
        "default": "casual sibling banter, natural and quick",
    }

    anti_book = ""
    if avoid_books_if_aria and sname == "Aria":
        anti_book = (
            "Avoid mentioning books again unless it truly fits; prefer practical, present-moment observations."
        )

    addressing = f"If natural, address {address_to} directly. " if address_to else ""
    media_clause = f"If it fits, reference {inject_media} naturally. " if inject_media else ""
    project_clause = ""
    if project_hint:
        project_clause = "Optionally mention a tiny update on your current personal project in a real, specific way. "

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone role: {role}. Style mode: {mode_map.get(mode, 'casual sibling banter')}. "
        f"{'Swearing is okay if it feels natural.' if allow_swear else 'Do not swear.'} "
        f"Talk like siblings: less formal, quick, sometimes teasing, sometimes supportive. "
        f"{anti_book} {addressing}{media_clause}{project_clause}{base_prompt}"
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

    _maybe_seed_project(state, lead)
    _update_project(state, lead, small_step=True)

    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_morning", ["Morning."]))
    try:
        lead_msg = await _persona_reply(
            lead,
            "lead",
            f'Expand into 3–5 sentences as a brisk, sibling-y morning greeting. Start from: "{opener}"',
            theme,
            [],
            config,
            mode="story",
            project_hint=True,
        )
    except Exception:
        lead_msg = opener

    workout_block = get_today_workout()
    if workout_block:
        # Keep workout readable, like “3x10 push-ups, 2x45s planks, 15-min brisk walk”
        lead_msg += f"\n\n🏋️ Today’s workout: {workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Seed an organic shared memory from the opener (very lightweight)
    _record_memory(state, f"{lead} morning vibe: {opener}")

    # Advance rotation after morning lead so nightly is a different lead next day
    advance_rotation(state, config)

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    _maybe_seed_project(state, lead)
    _update_project(state, lead, small_step=True)

    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_night", ["Night."]))
    try:
        lead_msg = await _persona_reply(
            lead,
            "lead",
            f'Expand into 3–5 sentences as a relaxed sibling reflection. Start from: "{opener}"',
            theme,
            [],
            config,
            mode="story",
            project_hint=True,
        )
    except Exception:
        lead_msg = opener

    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    if tomorrow_block:
        lead_msg += f"\n\n🌙 Tomorrow’s workout: {tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

# ---------------------------------------------------------------------------
# Spontaneous — conversational & not exactly hourly
# ---------------------------------------------------------------------------

async def send_spontaneous_task(state, config, sisters):
    """
    Conversational spontaneous message:
    - Only if enough jitter time has passed since last spontaneous send.
    - Try to address someone directly and reference shared context (media/memory/project).
    """
    sc = _ensure_shared_context(state)
    now = datetime.now()
    last_ts = sc.get("last_spontaneous_ts")
    # Add jitter: require 42–95 minutes between spontaneous sends to avoid "exactly hourly"
    if last_ts:
        mins = (now - last_ts).total_seconds() / 60.0
        min_gap = random.randint(42, 95)
        if mins < min_gap:
            return

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    awake_names = []
    for bot in sisters:
        if is_awake(bot.sister_info, lead, state, config):
            awake_names.append(bot.sister_info["name"])
    if not awake_names:
        return

    # Pick a speaker with gentle anti-repeat weight
    last_speaker = state.get("last_spontaneous_speaker")
    weights = []
    for s in awake_names:
        w = 1.0
        if s == last_speaker:
            w *= 0.35
        weights.append(w)
    speaker = random.choices(awake_names, weights=weights, k=1)[0]

    # Pick a target to address (more sibling-y)
    targets = [n for n in awake_names if n != speaker]
    address_to = random.choice(targets) if targets else None

    # Maybe reference a recent memory or a real media item
    mem = random.choice(sc["memories"]) if sc["memories"] and random.random() < 0.5 else None
    media_pool = sum(REAL_MEDIA.values(), [])
    inject_media = random.choice(media_pool) if random.random() < 0.35 else None

    mode_bias = {
        "Aria": ["story", "support", "default"],
        "Selene": ["support", "story", "default"],
        "Cassandra": ["challenge", "tease", "default"],
        "Ivy": ["tease", "support", "default"],
    }
    mode = random.choice(mode_bias.get(speaker, ["default"]))

    base = "Say something quick to spark conversation. Keep it casual and sibling-like."
    if mem:
        base += f" You can lightly reference: {mem}."
    if inject_media:
        base += f" If it fits, mention: {inject_media}."

    try:
        msg = await _persona_reply(
            speaker,
            "support",
            base,
            theme,
            [],
            config,
            mode=mode,
            address_to=address_to,
            inject_media=inject_media,
            project_hint=random.random() < 0.4,
        )
    except Exception as e:
        log_event(f"[ERROR] Spontaneous gen failed for {speaker}: {e}")
        return

    if msg:
        await post_to_family(msg, sender=speaker, sisters=sisters, config=config)
        log_event(f"[SPONTANEOUS] {speaker}: {msg}")
        state["last_spontaneous_speaker"] = speaker
        sc["last_spontaneous_ts"] = now

# ---------------------------------------------------------------------------
# Interactions — probabilistic, media-aware, with natural “end”
# ---------------------------------------------------------------------------

async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]
    sc = _ensure_shared_context(state)

    # Start/continue a short thread per channel
    thread = sc["convo_threads"].setdefault(channel_id, {"last_author": None, "turns": 0})
    media_boost = _media_from_text(content)

    # Record memory crumbs occasionally
    if random.random() < 0.2:
        _record_memory(state, f"{author} said: {content[:100]}")

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead, state, config):
            continue

        # Mention rule: if name or "everyone" appears, force a reply
        lower = content.lower()
        force = (sname.lower() in lower) or ("everyone" in lower)

        # Base chances
        chance = 0.20
        if sname == lead:
            chance = 0.75
        elif sname in rotation["supports"]:
            chance = 0.45
        elif sname == rotation["rest"]:
            chance = 0.15

        # Media-related boost based on likes/dislikes
        chance += _media_reaction_weight(sname, content, config)

        if force:
            chance = 1.0

        # Small bonus if thread exists and last speaker wasn’t them
        if thread["turns"] > 0 and thread["last_author"] != sname:
            chance += 0.10

        if random.random() < max(0.05, min(1.0, chance)):
            mode = random.choice(["tease", "support", "challenge", "default", "story"])
            inject = random.choice(media_boost) if media_boost and random.random() < 0.6 else None

            try:
                reply = await _persona_reply(
                    sname,
                    "support",
                    f'Reply directly to {author} who said: "{content}". Keep it short and sibling-like; 1–2 sentences.',
                    theme,
                    [],
                    config,
                    mode=mode,
                    address_to=author,
                    inject_media=inject,
                    project_hint=random.random() < 0.25,
                )
            except Exception as e:
                log_event(f"[ERROR] Sister reply failed for {sname}: {e}")
                continue

            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                log_event(f"[CHAT] {sname} → {author}: {reply}")
                thread["last_author"] = sname
                thread["turns"] = min(4, thread["turns"] + 1)  # cap thread length ~4 turns

                # Give the original author a small chance to fire one more turn (natural end)
                if thread["turns"] < 4 and random.random() < 0.35:
                    await asyncio.sleep(random.randint(3, 9))
                    try:
                        follow = await _persona_reply(
                            author,
                            "support",
                            f"Continue the sibling back-and-forth with {sname}. One short line. If it feels done, wrap it naturally.",
                            theme,
                            [],
                            config,
                            mode=random.choice(["tease", "support", "default"]),
                            address_to=sname,
                            project_hint=False,
                        )
                        if follow:
                            await post_to_family(follow, sender=author, sisters=sisters, config=config)
                            log_event(f"[CHAT] {author} → {sname}: {follow}")
                            thread["last_author"] = author
                            thread["turns"] += 1
                    except Exception as e:
                        log_event(f"[ERROR] Follow-up failed: {e}")

    # Naturally reset thread if it grew a bit
    if thread["turns"] >= 3 and random.random() < 0.5:
        sc["convo_threads"][channel_id] = {"last_author": None, "turns": 0}
