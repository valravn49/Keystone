import json
import os
import random
import asyncio
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

# If you have a real image backend, provide image_utils.generate_from_portrait
try:
    import image_utils  # must expose: generate_from_portrait(base_path, prompt, save_path) -> str|None
except Exception:
    image_utils = None

AEDT = ZoneInfo("Australia/Sydney")

# ---------------------------------------------------------------------------
# Ritual opener variations (short + siblingy)
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
# Paths for JSON memory/personality + portraits/outfits
# ---------------------------------------------------------------------------

PERSONALITY_DIR = "/Autonomy/personalities"
MEMORY_DIR = "/Autonomy/memory"
PORTRAIT_DIR = "/Autonomy/portraits"
OUTFIT_DIR = "/Autonomy/outfits"

def _personality_path(name: str) -> str:
    return os.path.join(PERSONALITY_DIR, f"{name}.json")

def _memory_path(name: str) -> str:
    return os.path.join(MEMORY_DIR, f"{name}.json")

def _portrait_path(name: str) -> str:
    # Sisters use single portrait file: {Name}_Portrait.png
    return os.path.join(PORTRAIT_DIR, f"{name}_Portrait.png")

def _outfit_path_for(name: str, dt: datetime) -> str:
    day = dt.astimezone(AEDT).date().isoformat()
    outdir = os.path.join(OUTFIT_DIR, name)
    os.makedirs(outdir, exist_ok=True)
    return os.path.join(outdir, f"{day}_outfit.png")

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _read_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] JSON read fail {path}: {e}")
    return default

def _write_json(path: str, payload: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] JSON write fail {path}: {e}")

def load_persona(name: str) -> dict:
    return _read_json(_personality_path(name), {
        "name": name,
        "likes": [],
        "dislikes": [],
        "speech_examples": [],
        "core_personality": ""
    })

def load_memory(name: str) -> dict:
    return _read_json(_memory_path(name), {
        "projects": {},
        "recent_notes": [],
        "last_outfit_prompt": None
    })

def save_memory(name: str, memo: dict):
    _write_json(_memory_path(name), memo)

# ---------------------------------------------------------------------------
# Rotation / awake scheduling (AEDT)
# ---------------------------------------------------------------------------

def _assign_today_schedule(name: str, state: dict, config: dict):
    key, kdate = f"{name}_schedule", f"{name}_schedule_date"
    today = datetime.now(AEDT).date()
    if state.get(kdate) == today and key in state:
        return state[key]
    sch = (config.get("schedules", {}) or {}).get(name, {"wake": [6, 8], "sleep": [22, 23]})
    def pick(span): lo, hi = int(span[0]), int(span[1]); return random.randint(lo, hi) if hi >= lo else lo
    state[key] = {"wake": pick(sch.get("wake", [6,8])), "sleep": pick(sch.get("sleep", [22,23]))}
    state[kdate] = today
    return state[key]

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep: return True
    if wake < sleep: return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_awake(sister_info, lead_name, state=None, config=None):
    if sister_info["name"] == lead_name:
        return True
    sc = _assign_today_schedule(sister_info["name"], state or {}, config or {})
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

def get_today_rotation(state, config):
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    names = [s["name"] for s in config["rotation"]]
    lead = names[idx]
    rest = names[(idx + 1) % len(names)]
    supports = [n for n in names if n not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation(state, config):
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])

def get_current_theme(state, config):
    today = datetime.now(AEDT).date()
    if state.get("last_theme_update") is None or (today.weekday() == 0 and state.get("last_theme_update") != today):
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
                log_event(f"[ERROR] {sender} send failed: {e}")
            break

# ---------------------------------------------------------------------------
# Media / memory context (kept small and real-feeling)
# ---------------------------------------------------------------------------

REAL_MEDIA = {
    "games": [
        "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
        "Stardew Valley", "Hollow Knight", "Elden Ring", "Overwatch 2"
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
    sc.setdefault("memories", [])
    sc.setdefault("projects", {})        # {name: dict}
    sc.setdefault("last_spontaneous_ts", None)
    sc.setdefault("convo_threads", {})  # {channel_id: {last_author, turns}}
    return sc

def _record_memory(state: dict, text: str):
    sc = _ensure_shared_context(state)
    sc["memories"] = (sc["memories"] + [text])[-50:]

def _maybe_seed_project(state: dict, name: str):
    sc = _ensure_shared_context(state)
    if name not in sc["projects"]:
        seeds = {
            "Aria": {"title": "Weekly planner revamp", "progress": round(random.uniform(0.2, 0.6), 2), "note": "color tabs and layouts"},
            "Selene": {"title": "Comfort-food recipe cards", "progress": round(random.uniform(0.3, 0.7), 2), "note": "handwritten set"},
            "Cassandra": {"title": "Shelf re-organization", "progress": round(random.uniform(0.5, 0.9), 2), "note": "labeling lower drawers"},
            "Ivy": {"title": "Closet restyle challenge", "progress": round(random.uniform(0.1, 0.5), 2), "note": "mismatch fits on purpose"},
        }
        sc["projects"][name] = seeds.get(name, {"title": "Personal task", "progress": 0.3, "note": "initial setup"})

def _update_project(state: dict, name: str, small_step=True):
    sc = _ensure_shared_context(state)
    _maybe_seed_project(state, name)
    pj = sc["projects"].get(name)
    if not pj: return
    delta = random.uniform(0.02, 0.08) if small_step else random.uniform(0.08, 0.18)
    pj["progress"] = float(max(0.0, min(1.0, round(pj["progress"] + delta, 2))))

def _media_from_text(text: str) -> list:
    hits, lower = [], text.lower()
    for items in REAL_MEDIA.values():
        for it in items:
            if it.lower() in lower:
                hits.append(it)
    return list(set(hits))

def _media_reaction_weight(name: str, text: str, config: dict) -> float:
    persona = load_persona(name)
    likes = " ".join(persona.get("likes", [])).lower()
    dislikes = " ".join(persona.get("dislikes", [])).lower()
    boost = 0.0
    for m in _media_from_text(text):
        if any(w in likes for w in m.lower().split()):
            boost += 0.25
        if any(w in dislikes for w in m.lower().split()):
            boost -= 0.20
    return boost

# ---------------------------------------------------------------------------
# Persona wrapper (anti “Aria keeps talking about books” bias)
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
        "support": "encouraging, warm, a little teasing if natural",
        "tease": "poke fun, playful/bratty sibling energy (kind underneath)",
        "challenge": "blunt or scolding like a strict sibling (not cruel)",
        "story": "share a tiny, realistic anecdote or throwback memory",
        "default": "casual sibling banter; quick, natural",
    }

    anti_book = ""
    if sname == "Aria":
        anti_book = "Avoid leaning on books unless it truly fits; prefer present-moment, practical observations."

    addressing = f"Address {address_to} directly if it feels natural. " if address_to else ""
    media_clause = f"If it fits, reference {inject_media} naturally. " if inject_media else ""
    proj_clause = "Optionally mention a real-feeling micro-update on your personal project. " if project_hint else ""

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone role: {role}. Style mode: {mode_map.get(mode, 'casual sibling banter')}. "
        f"{'Mild swearing is okay if natural.' if allow_swear else 'Do not swear.'} "
        f"Talk like siblings (banter, small teasing, warm/familiar). "
        f"{anti_book} {addressing}{media_clause}{proj_clause}{base_prompt}"
    )

    return await generate_llm_reply(
        sister=sname,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )

# ---------------------------------------------------------------------------
# Outfit generation (portrait-based). Safe fallback if backend unavailable.
# ---------------------------------------------------------------------------

async def generate_and_post_outfit(name: str, sisters, config, prompt_hint: str | None = None):
    """
    Creates a day outfit image from the sibling's base portrait and posts it.
    - Portrait: /Autonomy/portraits/{Name}_Portrait.png
    - Save to:  /Autonomy/outfits/{Name}/YYYY-MM-DD_outfit.png
    - Stores 'last_outfit_prompt' in memory JSON.
    """
    base_path = _portrait_path(name)
    save_path = _outfit_path_for(name, datetime.now(AEDT))
    mem = load_memory(name)

    # Basic personality-informed defaults
    persona = load_persona(name)
    season = _season_descriptor()
    style_line = _style_line_for(name, persona)

    # Prompt to the image system
    outfit_prompt = (
        prompt_hint
        or f"{name}'s outfit today ({season}): {style_line}. Full-body outfit render, consistent with portrait."
    )

    mem["last_outfit_prompt"] = outfit_prompt
    save_memory(name, mem)

    if image_utils and hasattr(image_utils, "generate_from_portrait") and os.path.exists(base_path):
        try:
            out = image_utils.generate_from_portrait(
                base_portrait_path=base_path,
                outfit_prompt=outfit_prompt,
                save_path=save_path
            )
            if out:
                await post_to_family(f"🧵 {name} — today’s fit:", name, sisters, config)
                await _post_image_file(name, sisters, config, out)
                log_event(f"[OUTFIT] {name} generated: {out}")
                return out
        except Exception as e:
            log_event(f"[ERROR] Outfit gen failed for {name}: {e}")

    # Fallback (no backend)
    await post_to_family(f"🧵 {name} — today’s fit: {style_line} ({season})", name, sisters, config)
    log_event(f"[OUTFIT-FALLBACK] {name}: {style_line}")
    return None

async def _post_image_file(sender: str, sisters, config, path: str):
    # Discord file post via correct bot instance
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch and os.path.exists(path):
                    import discord
                    file = discord.File(path, filename=os.path.basename(path))
                    await ch.send(file=file)
            except Exception as e:
                log_event(f"[ERROR] image send failed for {sender}: {e}")
            break

def _season_descriptor() -> str:
    dt = datetime.now(AEDT)
    m = dt.month
    # Southern hemisphere seasons
    if m in (12,1,2): return "summer"
    if m in (3,4,5): return "autumn"
    if m in (6,7,8): return "winter"
    return "spring"

def _style_line_for(name: str, persona: dict) -> str:
    # Small, personality-aligned defaults
    base = {
        "Aria": "soft knit top, pleated skirt, tidy layers, muted palette",
        "Selene": "cozy cardigan, relaxed slacks or long skirt, gentle colors",
        "Cassandra": "structured top, fitted pants, clean lines, minimal palette",
        "Ivy": "playful crop or oversized top, statement skirt/shorts, mischievous accessories",
    }
    return base.get(name, "casual, personality-aligned fit")

# ---------------------------------------------------------------------------
# Rituals (morning/night) — generate outfits in morning; siblings reply naturally
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
            lead, "lead",
            f'Expand into 3–5 sentences as a brisk siblingy morning greeting. Start from: "{opener}"',
            theme, [], config, mode="story", project_hint=True
        )
    except Exception:
        lead_msg = opener

    workout_block = get_today_workout()
    if workout_block:
        lead_msg += f"\n\n🏋️ Today’s workout: {workout_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # Generate & post today's outfit for lead
    await generate_and_post_outfit(lead, sisters, config)

    # Everyone else has a chance to post their outfit in the morning too
    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == lead: continue
        if is_awake(bot.sister_info, lead, state, config) and random.random() < 0.65:
            await asyncio.sleep(random.randint(2, 10))
            await generate_and_post_outfit(sname, sisters, config)

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

    tomorrow = datetime.now(AEDT).date() + timedelta(days=1)
    tomorrow_block = get_today_workout(tomorrow)
    if tomorrow_block:
        lead_msg += f"\n\n🌙 Tomorrow’s workout: {tomorrow_block}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

# ---------------------------------------------------------------------------
# Spontaneous chat (not exactly hourly) + midday outfit changes
# ---------------------------------------------------------------------------

async def send_spontaneous_task(state, config, sisters):
    sc = _ensure_shared_context(state)
    now = datetime.now(AEDT)
    last_ts = sc.get("last_spontaneous_ts")
    if last_ts:
        mins = (now - last_ts).total_seconds() / 60.0
        min_gap = random.randint(42, 95)
        if mins < min_gap:
            return

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    awake = [b.sister_info["name"] for b in sisters if is_awake(b.sister_info, lead, state, config)]
    if not awake:
        return

    last_speaker = state.get("last_spontaneous_speaker")
    weights = [(0.35 if n == last_speaker else 1.0) for n in awake]
    speaker = random.choices(awake, weights=weights, k=1)[0]

    targets = [n for n in awake if n != speaker]
    address_to = random.choice(targets) if targets else None

    # 35% chance the spontaneous event is an outfit change instead of a chat line
    if random.random() < 0.35:
        await generate_and_post_outfit(speaker, sisters, config, prompt_hint=None)
        sc["last_spontaneous_ts"] = now
        state["last_spontaneous_speaker"] = speaker
        return

    mode_bias = {
        "Aria": ["story","support","default"],
        "Selene": ["support","story","default"],
        "Cassandra": ["challenge","tease","default"],
        "Ivy": ["tease","support","default"],
    }
    mode = random.choice(mode_bias.get(speaker, ["default"]))

    base = "Say something quick to start a siblingy mini-convo. Tease/play nice as fits."
    try:
        msg = await _persona_reply(
            speaker, "support",
            base, theme, [], config,
            mode=mode, address_to=address_to,
            project_hint=(random.random() < 0.4)
        )
    except Exception as e:
        log_event(f"[ERROR] spontaneous gen {speaker}: {e}")
        return

    if msg:
        await post_to_family(msg, sender=speaker, sisters=sisters, config=config)
        log_event(f"[SPONTANEOUS] {speaker}: {msg}")
        sc["last_spontaneous_ts"] = now
        state["last_spontaneous_speaker"] = speaker

# ---------------------------------------------------------------------------
# Interactions — sibling back-and-forth with natural end
# ---------------------------------------------------------------------------

async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]
    sc = _ensure_shared_context(state)

    thread = sc["convo_threads"].setdefault(channel_id, {"last_author": None, "turns": 0})

    # Light memory crumb
    if random.random() < 0.2:
        _record_memory(state, f"{author} said: {content[:120]}")

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead, state, config):
            continue

        lower = content.lower()
        force = (sname.lower() in lower) or ("everyone" in lower)

        chance = 0.22
        if sname == lead:
            chance = 0.75
        elif sname in rotation["supports"]:
            chance = 0.45
        elif sname == rotation["rest"]:
            chance = 0.18

        chance += _media_reaction_weight(sname, content, config)

        if force:
            chance = 1.0

        if thread["turns"] > 0 and thread["last_author"] != sname:
            chance += 0.10

        if random.random() < max(0.05, min(1.0, chance)):
            mode = random.choice(["tease","support","challenge","default","story"])
            inject = None
            mf = _media_from_text(content)
            if mf and random.random() < 0.6:
                inject = random.choice(mf)

            try:
                reply = await _persona_reply(
                    sname, "support",
                    f'Reply to {author} who said: "{content}". Keep it short (1–2 sentences) and sibling-like.',
                    theme, [], config,
                    mode=mode, address_to=author, inject_media=inject,
                    project_hint=(random.random() < 0.25)
                )
            except Exception as e:
                log_event(f"[ERROR] reply fail {sname}: {e}")
                continue

            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                log_event(f"[CHAT] {sname} → {author}: {reply}")
                thread["last_author"] = sname
                thread["turns"] = min(4, thread["turns"] + 1)

                # One more natural turn from the original author with small chance
                if thread["turns"] < 4 and random.random() < 0.35:
                    await asyncio.sleep(random.randint(3, 9))
                    try:
                        follow = await _persona_reply(
                            author, "support",
                            f"Continue a tiny back-and-forth with {sname}. If it feels done, wrap naturally.",
                            theme, [], config,
                            mode=random.choice(["tease","support","default"]),
                            address_to=sname
                        )
                        if follow:
                            await post_to_family(follow, sender=author, sisters=sisters, config=config)
                            log_event(f"[CHAT] {author} → {sname}: {follow}")
                            thread["last_author"] = author
                            thread["turns"] += 1
                    except Exception as e:
                        log_event(f"[ERROR] follow fail: {e}")

    if thread["turns"] >= 3 and random.random() < 0.5:
        sc["convo_threads"][channel_id] = {"last_author": None, "turns": 0}
