# sisters_behavior.py
import json
import os
import random
import asyncio
from datetime import datetime, timedelta, time

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# If your relationships module is present, these imports will work.
# If not, we keep calls guarded so the rest still runs.
try:
    from relationships import adjust_relationship, plot_relationships
except Exception:
    adjust_relationship = None
    plot_relationships = None

# =============================================================================
# Persona OPENERS (varied lines so Cass doesn't repeat and Aria doesn't say "book" every time)
# =============================================================================
PERSONA_TONES = {
    "Aria": {
        "intro_morning": [
            "Morning — trying to keep it quiet and steady.",
            "Good morning. Tea first, then I’ll be useful.",
            "Morning. Windows open, fresh air, slow start.",
        ],
        "intro_night": [
            "Time to wind down. Lights low, mind softer.",
            "Good night — it was calm enough today.",
            "I’m turning in. Shoes by the door, everything in its place.",
        ],
    },
    "Selene": {
        "intro_morning": [
            "Morning, darlings — water and a bite before you bolt.",
            "Good morning. Be gentle with your head today.",
            "Morning, loves. I made a short list so you don’t forget things.",
        ],
        "intro_night": [
            "Good night, sweet ones. Find your blankets.",
            "Sleep well — proud of your little wins today.",
            "Night night — quiet breaths, slow and warm.",
        ],
    },
    "Cassandra": {
        "intro_morning": [
            "Up. The day won’t wait.",
            "Morning. Keep it tight; no dithering.",
            "Move. Momentum, then results.",
        ],
        "intro_night": [
            "Done. Review, then sleep.",
            "The day’s over. Don’t slack tomorrow.",
            "Close it out. Be sharper in the morning.",
        ],
    },
    "Ivy": {
        "intro_morning": [
            "Ugh, fine, hi~ Coffee me, gremlins.",
            "Morning~ I’m calling dibs on the mirror.",
            "Good morniiing! If you’re slow I will heckle you.",
        ],
        "intro_night": [
            "Night night! Don’t snore or I’ll record it.",
            "Okay bedtime — I’m stealing the fluffy blanket.",
            "Sleep tight~ I’m haunting your dreams.",
        ],
    },
}

# =============================================================================
# Configurable “real” media pool (siblings react based on likes/dislikes)
# =============================================================================
REAL_MEDIA = {
    "games": [
        "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
        "Stardew Valley", "Elden Ring", "Hollow Knight", "Overwatch 2"
    ],
    "anime": [
        "Attack on Titan", "Demon Slayer", "Jujutsu Kaisen", "My Hero Academia", "Spy x Family"
    ],
    "music": [
        "lofi hip hop", "indie pop playlists", "Ghibli soundtracks", "synthwave"
    ],
    "shows": [
        "The Mandalorian", "Arcane", "The Last of Us", "Stranger Things"
    ]
}
MEDIA_FLAT = sum(REAL_MEDIA.values(), [])

# =============================================================================
# Optional JSON persona + memory (safe fallbacks if missing)
# =============================================================================
def _profile_path(name: str) -> str:
    return f"/mnt/data/{name}_Personality.json"

def _memory_path(name: str) -> str:
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
    data = _load_json(_profile_path(name), {
        "name": name,
        "core_personality": "",
        "likes": [],
        "dislikes": [],
        "speech_examples": []
    })
    data.setdefault("likes", [])
    data.setdefault("dislikes", [])
    data.setdefault("speech_examples", [])
    return data

def load_memory(name: str) -> dict:
    memo = _load_json(_memory_path(name), {"projects": {}, "recent_notes": []})
    memo.setdefault("projects", {})
    memo.setdefault("recent_notes", [])
    return memo

def save_memory(name: str, memo: dict) -> None:
    try:
        path = _memory_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memo, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Failed writing memory for {name}: {e}")

# =============================================================================
# Scheduling / Awake logic (uses config["schedules"][Name] hour windows)
# =============================================================================
def _assign_today_schedule(name: str, state: dict, config: dict):
    key, kd = f"{name}_schedule", f"{name}_schedule_date"
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

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep:
        return True
    if wake < sleep:
        return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_awake(sister_info, lead_name, state=None, config=None):
    # Lead is always "awake" for ritual starters
    if sister_info["name"] == lead_name:
        return True
    if state is None or config is None:
        # Legacy fallback (fixed times)
        now = datetime.now().time()
        wake = datetime.strptime(sister_info.get("wake", "06:00"), "%H:%M").time()
        bed = datetime.strptime(sister_info.get("bed", "22:00"), "%H:%M").time()
        return (wake <= now <= bed) if wake <= bed else (now >= wake or now <= bed)

    sc = _assign_today_schedule(sister_info["name"], state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# =============================================================================
# Rotation / theme helpers
# =============================================================================
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

# =============================================================================
# Shared conversation context
# =============================================================================
def _ensure_shared_context(state: dict):
    sc = state.setdefault("shared_context", {})
    sc.setdefault("memories", [])                # small strings of recent moments
    sc.setdefault("projects", {})                # {name: {title, progress, note}}
    sc.setdefault("last_spontaneous_ts", None)   # jitter gates spontaneous posts
    sc.setdefault("convo_threads", {})           # {channel_id: {"last_author":..., "turns": int}}
    sc.setdefault("conversation_topic", None)    # auto-detected topic label
    return sc

def _record_memory(state: dict, text: str):
    sc = _ensure_shared_context(state)
    sc["memories"] = (sc.get("memories", []) + [text])[-50:]

def _maybe_seed_project(state: dict, name: str):
    sc = _ensure_shared_context(state)
    if name not in sc["projects"]:
        seeds = {
            "Aria": {"title": "Planner revamp", "progress": round(random.uniform(0.25, 0.55), 2), "note": "tabs & layouts"},
            "Selene": {"title": "Comfort recipe cards", "progress": round(random.uniform(0.30, 0.70), 2), "note": "handwritten set"},
            "Cassandra": {"title": "Shelf re-organization", "progress": round(random.uniform(0.45, 0.85), 2), "note": "drawer labels"},
            "Ivy": {"title": "Closet restyle challenge", "progress": round(random.uniform(0.15, 0.45), 2), "note": "mismatch fits on purpose"},
        }
        sc["projects"][name] = seeds.get(name, {"title": "Small personal task", "progress": 0.3, "note": "low-key"})

def _update_project(state: dict, name: str, small_step: bool = True):
    sc = _ensure_shared_context(state)
    _maybe_seed_project(state, name)
    pj = sc["projects"].get(name)
    if not pj:
        return
    delta = random.uniform(0.02, 0.08) if small_step else random.uniform(0.08, 0.16)
    pj["progress"] = max(0.0, min(1.0, round(pj["progress"] + delta, 2)))

def _media_hits(text: str) -> list:
    lower = text.lower()
    hits = [m for m in MEDIA_FLAT if m.lower() in lower]
    # dedupe while preserving order
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out

def _media_weight_for(name: str, text: str) -> float:
    persona = load_persona(name)
    likes = " ".join(persona.get("likes", [])).lower()
    dislikes = " ".join(persona.get("dislikes", [])).lower()
    hits = _media_hits(text)
    boost = 0.0
    for h in hits:
        tokens = h.lower().split()
        if any(t in likes for t in tokens):
            boost += 0.25
        if any(t in dislikes for t in tokens):
            boost -= 0.20
    return boost

# =============================================================================
# Automatic conversation-topic detection (Option A)
# =============================================================================
TOPIC_KEYWORDS = {
    "food": ["cook", "recipe", "eat", "snack", "lunch", "dinner", "breakfast", "coffee", "tea"],
    "plans": ["plan", "schedule", "tonight", "weekend", "tomorrow", "later", "arrange"],
    "games": ["game", "zelda", "final fantasy", "elden ring", "overwatch", "hollow knight", "steam"],
    "anime": ["anime", "attack on titan", "demon slayer", "jujutsu kaisen", "my hero", "spy x family"],
    "music": ["music", "playlist", "song", "soundtrack", "ghibli", "synthwave", "lofi"],
    "fitness": ["workout", "run", "gym", "push-up", "walk", "yoga", "stretch"],
    "house": ["clean", "shelf", "closet", "tidy", "organize", "laundry", "room", "desk"]
}

def _infer_topic_from_text(text: str) -> str | None:
    t = text.lower()
    scores = {k: 0 for k in TOPIC_KEYWORDS}
    for label, words in TOPIC_KEYWORDS.items():
        for w in words:
            if w in t:
                scores[label] += 1
    # choose highest nonzero
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else None

def _update_conversation_topic(state: dict, content: str):
    sc = _ensure_shared_context(state)
    topic = _infer_topic_from_text(content)
    # light hysteresis: only update if new or we’ve had no topic recently
    if topic and (sc.get("conversation_topic") != topic or random.random() < 0.25):
        sc["conversation_topic"] = topic
        log_event(f"[TOPIC] Conversation topic set to: {topic}")

# =============================================================================
# Persona wrapper — sibling vibe (Aria anti-book bias)
# =============================================================================
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
        "support": "encouraging and warm with light teasing",
        "tease": "playful/bratty sibling energy, never cruel",
        "challenge": "blunt or scolding like a strict sibling, but fair",
        "story": "share a tiny real-feeling anecdote/memory",
        "default": "casual sibling banter",
    }

    anti_book = ""
    if sname == "Aria":
        anti_book = "Avoid book talk unless it truly fits; favor practical, present details."

    addressing = f"If natural, address {address_to} directly. " if address_to else ""
    media_clause = f"If it fits, reference {inject_media} naturally. " if inject_media else ""
    project_clause = "Optionally mention a tiny, specific update on your personal project. " if project_hint else ""

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone role: {role}. Style mode: {mode_map.get(mode, 'casual sibling banter')}. "
        f"{'Swearing is okay if mild/natural.' if allow_swear else 'Do not swear.'} "
        f"Speak like a real sibling: quick, natural, sometimes teasing, sometimes soft. "
        f"{anti_book} {addressing}{media_clause}{project_clause}{base_prompt}"
    )

    return await generate_llm_reply(
        sister=sname,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )

# =============================================================================
# Rituals
# =============================================================================
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    _maybe_seed_project(state, lead)
    _update_project(state, lead, small_step=True)

    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_morning", ["Morning."]))
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 sentences as a brisk, sibling-y morning greeting. Start from: "{opener}"',
            theme, [], config, mode="story", project_hint=True
        )
    except Exception:
        lead_msg = opener

    workout_block = get_today_workout()
    if workout_block:
        lead_msg += f"\n\n🏋️ Today’s workout: {workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)
    _record_memory(state, f"{lead} morning vibe: {opener}")

    # Optional daily relationship map (only if plotting module exists)
    if plot_relationships and random.random() < 0.25:
        try:
            img_path = plot_relationships(state)
            if img_path:
                await post_to_family(f"(relationship map saved: {img_path})", sender=lead, sisters=sisters, config=config)
        except Exception as e:
            log_event(f"[REL-VIZ] Failed to plot: {e}")

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
            lead, "lead",
            f'Expand into 3–5 sentences as a relaxed sibling reflection. Start from: "{opener}"',
            theme, [], config, mode="story", project_hint=True
        )
    except Exception:
        lead_msg = opener

    tomorrow = datetime.now().date() + timedelta(days=1)
    t_block = get_today_workout(tomorrow)
    if t_block:
        lead_msg += f"\n\n🌙 Tomorrow’s workout: {t_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

# =============================================================================
# Spontaneous — conversational, jittered (not exactly hourly)
# =============================================================================
async def send_spontaneous_task(state, config, sisters):
    sc = _ensure_shared_context(state)
    now = datetime.now()
    last_ts = sc.get("last_spontaneous_ts")
    if last_ts:
        mins = (now - last_ts).total_seconds() / 60.0
        min_gap = random.randint(42, 95)  # jitter gate
        if mins < min_gap:
            return

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    awake = [b.sister_info["name"] for b in sisters if is_awake(b.sister_info, lead, state, config)]
    if not awake:
        return

    # pick speaker with anti-repeat weight
    last_speaker = state.get("last_spontaneous_speaker")
    weights = []
    for n in awake:
        w = 1.0
        if n == last_speaker:
            w *= 0.35
        weights.append(w)
    speaker = random.choices(awake, weights=weights, k=1)[0]

    # address one sibling to spark back-and-forth
    targets = [n for n in awake if n != speaker]
    address_to = random.choice(targets) if targets else None

    # optionally reference memory or real media
    mem = random.choice(sc["memories"]) if sc["memories"] and random.random() < 0.4 else None
    inject_media = random.choice(MEDIA_FLAT) if random.random() < 0.35 else None

    mode_bias = {
        "Aria": ["story", "support", "default"],
        "Selene": ["support", "story", "default"],
        "Cassandra": ["challenge", "tease", "default"],
        "Ivy": ["tease", "support", "default"],
    }
    mode = random.choice(mode_bias.get(speaker, ["default"]))

    base = "Say something quick to spark a conversation. Keep it casual and sibling-like."
    if mem:
        base += f" You can nod to this: {mem}."
    if inject_media:
        base += f" If it fits, mention: {inject_media}."
    # topic steers phrasing slightly
    topic = _ensure_shared_context(state).get("conversation_topic")
    if topic:
        base += f" The current topic vibe feels like: {topic}."

    try:
        msg = await _persona_reply(
            speaker, "support", base, theme, [], config,
            mode=mode, address_to=address_to, inject_media=inject_media, project_hint=random.random() < 0.35
        )
    except Exception as e:
        log_event(f"[ERROR] Spontaneous gen failed: {e}")
        return

    if msg:
        await post_to_family(msg, sender=speaker, sisters=sisters, config=config)
        log_event(f"[SPONTANEOUS] {speaker}: {msg}")
        state["last_spontaneous_speaker"] = speaker
        sc["last_spontaneous_ts"] = now

# =============================================================================
# Interactions — automatic topic updates, media-aware, natural endings
# =============================================================================
async def handle_sister_message(state, config, sisters, author, content, channel_id: int):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]
    sc = _ensure_shared_context(state)

    # Update the auto conversation topic from the latest message
    _update_conversation_topic(state, content)

    # Seed a short log memory occasionally
    if random.random() < 0.2:
        _record_memory(state, f"{author}: {content[:120]}")

    # Thread state per channel to get short back-and-forth and then stop
    thread = sc["convo_threads"].setdefault(channel_id, {"last_author": None, "turns": 0})

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead, state, config):
            continue

        lower = content.lower()
        forced = (sname.lower() in lower) or ("everyone" in lower)

        # Base chance shaped by roles
        chance = 0.22
        if sname == lead:
            chance = 0.72
        elif sname in rotation["supports"]:
            chance = 0.48
        elif sname == rotation["rest"]:
            chance = 0.18

        # Media reaction bias (likes/dislikes)
        chance += _media_weight_for(sname, content)

        # Small boost if a thread is already going and this sibling wasn't last speaker
        if thread["turns"] > 0 and thread["last_author"] != sname:
            chance += 0.10

        # Mentions override
        if forced:
            chance = 1.0

        if random.random() < max(0.05, min(1.0, chance)):
            mode = random.choice(["tease", "support", "challenge", "default", "story"])
            inject = None
            hits = _media_hits(content)
            if hits and random.random() < 0.6:
                inject = random.choice(hits)

            try:
                reply = await _persona_reply(
                    sname, "support",
                    f'Reply to {author} who said: "{content}". Keep it short (1–2 sentences), sibling-like, not a therapy group.',
                    theme, [], config,
                    mode=mode, address_to=author, inject_media=inject, project_hint=(random.random() < 0.25)
                )
            except Exception as e:
                log_event(f"[ERROR] Sister reply failed for {sname}: {e}")
                continue

            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                log_event(f"[CHAT] {sname} → {author}: {reply}")
                thread["last_author"] = sname
                thread["turns"] = min(4, thread["turns"] + 1)

                # Let the original author reply once more (natural close) with small chance
                if thread["turns"] < 4 and random.random() < 0.35:
                    await asyncio.sleep(random.randint(3, 9))
                    try:
                        follow = await _persona_reply(
                            author, "support",
                            f"Continue the sibling back-and-forth with {sname} in one short line. If it feels done, end naturally.",
                            theme, [], config,
                            mode=random.choice(["tease", "support", "default"]), address_to=sname
                        )
                        if follow:
                            await post_to_family(follow, sender=author, sisters=sisters, config=config)
                            log_event(f"[CHAT] {author} → {sname}: {follow}")
                            thread["last_author"] = author
                            thread["turns"] += 1
                    except Exception as e:
                        log_event(f"[ERROR] Follow-up failed: {e}")

    # Periodically reset thread so chats don’t run forever
    if thread["turns"] >= 3 and random.random() < 0.5:
        sc["convo_threads"][channel_id] = {"last_author": None, "turns": 0}
