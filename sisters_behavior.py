# sisters_behavior.py
# Conversational sibling dynamics + outfit caps + AEDT-aware rituals

import json, os, random, asyncio
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

AEDT = ZoneInfo("Australia/Sydney")  # handles AEST/AEDT automatically

# ---------------- Personality opener variations ----------------
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

# ---------------- Per-sibling reply tempo (seconds) ----------------
# FAST = feels live (1-8s); MED = chatty (15-60s); SLOW = casual (2-6 min)
TEMPO = {
    "Aria":   {"fast": (4, 12),  "med": (40, 120), "slow": (180, 360)},
    "Selene": {"fast": (5, 15),  "med": (60, 150), "slow": (240, 420)},
    "Cassandra": {"fast": (2, 8), "med": (30, 90), "slow": (180, 360)},
    "Ivy":    {"fast": (1, 6),   "med": (25, 75),  "slow": (120, 300)},
}

def _tempo_range(name: str, band: str) -> tuple[int, int]:
    lo, hi = TEMPO.get(name, TEMPO["Aria"]).get(band, (30, 90))
    return lo, hi

# ---------------- Paths for optional JSONs ----------------
def _profile_path(name: str) -> str: return f"/Autonomy/personalities/{name}.json"
def _memory_path(name: str)  -> str: return f"/Autonomy/memory/{name}.json"

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] JSON read failed {path}: {e}")
    return default

def load_persona(name: str) -> dict:
    data = _load_json(_profile_path(name), {"name": name, "likes": [], "dislikes": [], "core_personality": ""})
    data.setdefault("likes", []); data.setdefault("dislikes", []); data.setdefault("core_personality", "")
    return data

def load_memory(name: str) -> dict:
    data = _load_json(_memory_path(name), {
        "projects": {},
        "recent_notes": [],
        "outfits": {"date": None, "count": 0}
    })
    data.setdefault("projects", {}); data.setdefault("recent_notes", [])
    data.setdefault("outfits", {"date": None, "count": 0})
    return data

def save_memory(name: str, memo: dict):
    try:
        os.makedirs("/Autonomy/memory", exist_ok=True)
        with open(_memory_path(name), "w", encoding="utf-8") as f:
            json.dump(memo, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Memory write failed for {name}: {e}")

# ---------------- Schedule helpers ----------------
def _assign_today_schedule(name: str, state: dict, config: dict):
    key, kd = f"{name}_schedule", f"{name}_schedule_date"
    today = datetime.now(AEDT).date()
    if state.get(kd) == today and key in state: return state[key]

    sch = (config.get("schedules", {}) or {}).get(name, {"wake": [6, 8], "sleep": [22, 23]})
    def pick(span): lo, hi = int(span[0]), int(span[1]); return random.randint(lo, hi) if hi >= lo else lo
    schedule = {"wake": pick(sch.get("wake", [6, 8])), "sleep": pick(sch.get("sleep", [22, 23]))}
    state[key] = schedule; state[kd] = today; return schedule

def is_awake(sis_info, lead_name, state=None, config=None):
    if sis_info["name"] == lead_name: return True
    sc = _assign_today_schedule(sis_info["name"], state or {}, config or {"schedules": {}})
    now_h = datetime.now(AEDT).hour
    wake, sleep = sc["wake"], sc["sleep"]
    if wake == sleep: return True
    if wake < sleep:  return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

# ---------------- Rotation & theme ----------------
def get_today_rotation(state, config):
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    names = [s["name"] for s in config["rotation"]]
    lead = names[idx]
    rest = names[(idx + 1) % len(names)]
    supports = [n for n in names if n not in (lead, rest)]
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
                log_event(f"[ERROR] Send fail {sender}: {e}")
            break

# ---------------- Shared context (memories, projects) ----------------
REAL_MEDIA = {
    "games": [
        "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
        "Stardew Valley", "Elden Ring", "Hollow Knight", "Overwatch 2"
    ],
    "anime": ["Attack on Titan", "Demon Slayer", "Jujutsu Kaisen", "My Hero Academia", "Spy x Family"],
    "music": ["lofi hip hop", "indie pop", "Ghibli soundtracks", "synthwave"],
    "shows": ["The Mandalorian", "Arcane", "The Last of Us", "Stranger Things"],
}

def _ensure_shared_context(state: dict):
    sc = state.setdefault("shared_context", {})
    sc.setdefault("memories", [])
    sc.setdefault("projects", {})
    sc.setdefault("convo_threads", {})  # {channel_id: {"turns":int,"last":name}}
    sc.setdefault("last_spontaneous_ts", None)
    return sc

def _record_memory(state: dict, text: str):
    sc = _ensure_shared_context(state)
    sc["memories"] = (sc["memories"] + [text])[-50:]

def _maybe_seed_project(state: dict, name: str):
    sc = _ensure_shared_context(state)
    if name in sc["projects"]: return
    seeds = {
        "Aria": {"title": "Weekly planner revamp", "progress": round(random.uniform(0.2, 0.6), 2), "note": "color tabs and layouts"},
        "Selene": {"title": "Comfort-food recipe cards", "progress": round(random.uniform(0.3, 0.7), 2), "note": "handwritten set"},
        "Cassandra": {"title": "Shelf re-organization", "progress": round(random.uniform(0.5, 0.9), 2), "note": "labeling lower drawers"},
        "Ivy": {"title": "Closet restyle challenge", "progress": round(random.uniform(0.1, 0.5), 2), "note": "chaos fits on purpose"},
    }
    sc["projects"][name] = seeds.get(name, {"title": "Small personal task", "progress": 0.3, "note": "low-key"})

def _media_from_text(text: str) -> list[str]:
    hits, low = [], text.lower()
    for cat in REAL_MEDIA.values():
        for it in cat:
            if it.lower() in low:
                hits.append(it)
    return list(set(hits))

def _media_bias(name: str, text: str) -> float:
    p = load_persona(name)
    likes = " ".join(p.get("likes", [])).lower()
    dislikes = " ".join(p.get("dislikes", [])).lower()
    bias = 0.0
    for m in _media_from_text(text):
        if any(w in likes for w in m.lower().split()): bias += 0.25
        if any(w in dislikes for w in m.lower().split()): bias -= 0.2
    return bias

# ---------------- Persona wrapper (sibling vibe) ----------------
async def _persona_reply(
    sname: str, role: str, base_prompt: str, theme: str, config: dict,
    mode: str = "default", address_to: str | None = None, avoid_books_if_aria: bool = True,
    inject_media: str | None = None, project_hint: bool = False
):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    mode_map = {
        "support": "encouraging, warm, a little teasing",
        "tease": "poke fun, bratty but affectionate",
        "challenge": "blunt, strict sibling tone (not cruel)",
        "story": "tiny anecdote or real-feeling moment",
        "default": "casual sibling banter",
    }

    anti_book = ""
    if avoid_books_if_aria and sname == "Aria":
        anti_book = "Avoid defaulting to books; prefer present, practical observations."

    addr = f"If natural, address {address_to} directly. " if address_to else ""
    media = f"If it fits, mention {inject_media}. " if inject_media else ""
    project = "Optionally add a tiny, specific update on your own project. " if project_hint else ""

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Role tone: {role}. Style mode: {mode_map.get(mode,'casual sibling banter')}. "
        f"{'Mild swearing allowed if natural.' if allow_swear else 'Do not swear.'} "
        f"Talk like siblings, not a support group. {anti_book} {addr}{media}{project}{base_prompt}"
    )

    return await generate_llm_reply(
        sister=sname, user_message=prompt, theme=theme, role=role, history=[],
    )

# ---------------- Rituals (AEDT) ----------------
async def send_morning_message(state, config, sisters):
    rot = get_today_rotation(state, config)
    theme, lead = get_current_theme(state, config), rot["lead"]
    _maybe_seed_project(state, lead)

    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_morning", ["Morning."]))
    try:
        msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 sentences as a brisk, sibling-y morning greeting. Start from: "{opener}"',
            theme, config, mode="story", project_hint=True
        )
    except Exception:
        msg = opener

    wb = get_today_workout()
    if wb: msg += f"\n\n🏋️ Today’s workout: {wb}"

    await post_to_family(msg, lead, sisters, config)
    append_ritual_log(lead, "lead", theme, msg)
    _record_memory(state, f"{lead} morning vibe: {opener}")
    advance_rotation(state, config)

async def send_night_message(state, config, sisters):
    rot = get_today_rotation(state, config)
    theme, lead = get_current_theme(state, config), rot["lead"]
    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_night", ["Night."]))
    try:
        msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 sentences as a relaxed sibling reflection. Start from: "{opener}"',
            theme, config, mode="story", project_hint=True
        )
    except Exception:
        msg = opener
    tw = get_today_workout(datetime.now(AEDT).date() + timedelta(days=1))
    if tw: msg += f"\n\n🌙 Tomorrow’s workout: {tw}"
    await post_to_family(msg, lead, sisters, config)
    append_ritual_log(lead, "lead", theme, msg)

# ---------------- Outfit posting (cap at 2/day) ----------------
async def maybe_post_outfit(name: str, state: dict, config: dict, sisters, text: str):
    mem = load_memory(name)
    today = datetime.now(AEDT).date().isoformat()
    if mem["outfits"]["date"] != today:
        mem["outfits"] = {"date": today, "count": 0}
    if mem["outfits"]["count"] >= 2:
        return  # daily cap reached
    await post_to_family(text, name, sisters, config)
    mem["outfits"]["count"] += 1
    save_memory(name, mem)

# ---------------- Spontaneous chat (non-hourly, uses tempo) ----------------
async def send_spontaneous_task(state, config, sisters):
    sc = _ensure_shared_context(state)
    now = datetime.now(AEDT)
    last = sc.get("last_spontaneous_ts")
    if last and (now - last).total_seconds() < random.randint(42*60, 95*60):
        return

    rot, theme = get_today_rotation(state, config), get_current_theme(state, config)
    lead = rot["lead"]
    awake = [b.sister_info["name"] for b in sisters if is_awake(b.sister_info, lead, state, config)]
    if not awake: return

    last_sis = state.get("last_spontaneous_speaker")
    weights = [(0.35 if n == last_sis else 1.0) for n in awake]
    speaker = random.choices(awake, weights=weights, k=1)[0]
    targets = [n for n in awake if n != speaker]
    address_to = random.choice(targets) if targets else None
    media = random.choice(sum(REAL_MEDIA.values(), [])) if random.random() < 0.35 else None

    mode_pick = {
        "Aria": ["story","support","default"],
        "Selene": ["support","story","default"],
        "Cassandra": ["challenge","tease","default"],
        "Ivy": ["tease","support","default"]
    }
    mode = random.choice(mode_pick.get(speaker, ["default"]))

    base = "Say something quick to spark conversation with a sibling. Keep it casual and real."
    if media: base += f" If it fits, mention {media}."

    try:
        msg = await _persona_reply(
            speaker, "support", base, theme, config,
            mode=mode, address_to=address_to, project_hint=random.random()<0.4
        )
    except Exception as e:
        log_event(f"[ERROR] Spontaneous gen {speaker}: {e}")
        return

    if msg:
        await post_to_family(msg, speaker, sisters, config)
        state["last_spontaneous_speaker"] = speaker
        sc["last_spontaneous_ts"] = now

# ---------------- Message interaction with back-and-forth ----------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    rot, theme = get_today_rotation(state, config), get_current_theme(state, config)
    lead = rot["lead"]
    sc = _ensure_shared_context(state)
    thread = sc["convo_threads"].setdefault(channel_id, {"turns": 0, "last": None})

    for bot in sisters:
        name = bot.sister_info["name"]
        if name == author or not is_awake(bot.sister_info, lead, state, config):
            continue

        lower = content.lower()
        force = (name.lower() in lower) or ("everyone" in lower)

        chance = 0.20
        if name == lead: chance = 0.75
        elif name in rot["supports"]: chance = 0.45
        elif name == rot["rest"]: chance = 0.15
        chance += _media_bias(name, content)
        if force: chance = 1.0
        if thread["turns"] > 0 and thread["last"] != name: chance += 0.10

        if random.random() < max(0.05, min(1.0, chance)):
            mode = random.choice(["tease","support","challenge","default","story"])
            reply = await _persona_reply(
                name, "support",
                f'Reply to {author} who said: "{content}". Keep it short (1–2 sentences) and sibling-like.',
                theme, config, mode=mode, address_to=author,
            )
            if reply:
                # pace per sibling: if they feel like quick hits, use fast; sometimes med/slow
                band = random.choices(["fast","med","slow"], weights=[0.5,0.35,0.15])[0]
                wait_lo, wait_hi = _tempo_range(name, band)
                await asyncio.sleep(random.randint(wait_lo, wait_hi))
                await post_to_family(reply, name, sisters, config)
                thread["turns"] = min(5, thread["turns"] + 1)
                thread["last"] = name

                # give author a chance to respond one more time (and end naturally)
                if thread["turns"] < 5 and random.random() < 0.4:
                    a_band = random.choices(["fast","med","slow"], weights=[0.6,0.3,0.1])[0]
                    a_lo, a_hi = _tempo_range(author, a_band)
                    await asyncio.sleep(random.randint(a_lo, a_hi))
                    follow = await _persona_reply(
                        author, "support",
                        f"Continue the quick back-and-forth with {name}. One short line, end naturally if it feels done.",
                        theme, config, mode=random.choice(["tease","support","default"]), address_to=name
                    )
                    if follow:
                        await post_to_family(follow, author, sisters, config)
                        thread["turns"] += 1
                        thread["last"] = author

    if thread["turns"] >= 3 and random.random() < 0.5:
        sc["convo_threads"][channel_id] = {"turns": 0, "last": None}
