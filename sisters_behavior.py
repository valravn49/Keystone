import json
import os
import random
import asyncio
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from llm import generate_llm_reply
from logger import log_event, append_ritual_log
from workouts import get_today_workout

AEDT = ZoneInfo("Australia/Sydney")   # used year-round to keep “ritual time” stable

# ---------------------------------------------------------------------------
# Ritual opener variations (short, siblingy)
# ---------------------------------------------------------------------------
PERSONA_TONES = {
    "Aria": {
        "intro_morning": [
            "Morning — I stayed up too late reorganizing notes again.",
            "Good morning. I’m keeping today quiet on purpose.",
            "Morning, coffee first… then brain."
        ],
        "intro_night": [
            "Time to rest. I’ll probably read a little before bed.",
            "Good night — today was steady enough.",
            "Lights out soon. Quiet is good."
        ],
    },
    "Selene": {
        "intro_morning": [
            "Morning, darlings — eat something before you rush off.",
            "Good morning — start slow, breathe.",
            "Morning, loves. Remember water and breakfast."
        ],
        "intro_night": [
            "Good night, sweet ones. Don’t forget blankets.",
            "Sleep well — be soft with yourselves.",
            "Night night — proud of little things today."
        ],
    },
    "Cassandra": {
        "intro_morning": [
            "Up. The day won’t wait.",
            "Morning. Let’s keep it tight.",
            "Move. Momentum matters."
        ],
        "intro_night": [
            "The day’s done. Don’t slack tomorrow.",
            "Turn in. Review and reset.",
            "Done. Sleep on it, wake sharper."
        ],
    },
    "Ivy": {
        "intro_morning": [
            "Ughhh are we awake? Fine — hi~",
            "Morning, gremlins. No dawdling or I’ll tease.",
            "Good morning~ I call dibs on the mirror."
        ],
        "intro_night": [
            "Night night! No snoring, I’m serious (I’m not).",
            "Okay bedtime — I’m stealing the fluffy blanket.",
            "Sleep tight~ I’m haunting your dreams."
        ],
    },
}

SIBLING_NAMES = {"Aria", "Selene", "Cassandra", "Ivy", "Will"}

# ---------------- AEDT helpers ----------------
def now_aedt() -> datetime:
    return datetime.now(AEDT)

def today_aedt():
    return now_aedt().date()

# ---------------- Profile/Memory (optional JSONs, safe defaults) -----------
def _profile_path(name: str) -> str:
    return f"/Autonomy/personalities/{name}.json"

def _memory_path(name: str) -> str:
    return f"/Autonomy/memory/{name}.json"

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] JSON read failed ({path}): {e}")
    return default

def load_persona(name: str) -> dict:
    data = _load_json(_profile_path(name), {
        "name": name, "likes": [], "dislikes": [], "speech_examples": [], "core_personality": ""
    })
    for k, v in (("likes", []), ("dislikes", []), ("speech_examples", []), ("core_personality", "")):
        data.setdefault(k, v)
    return data

# ---------------- Scheduling / Awake checks --------------------------------
def _assign_today_schedule(name: str, state: dict, config: dict):
    key = f"{name}_schedule"
    kd  = f"{key}_date"
    today = today_aedt()
    if state.get(kd) == today and key in state:
        return state[key]

    # config["schedules"][Name] = {"wake":[lo,hi], "sleep":[lo,hi]}  (hours in local AEDT)
    sch = (config.get("schedules", {}) or {}).get(name, {"wake": [6, 8], "sleep": [22, 23]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        return random.randint(lo, hi) if hi >= lo else lo

    schedule = {"wake": pick(sch.get("wake", [6, 8])), "sleep": pick(sch.get("sleep", [22, 23]))}
    state[key] = schedule
    state[kd]  = today
    log_event(f"[SCHED] {name} → {schedule} (AEDT)")
    return schedule

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep:  # degenerate “always on”
        return True
    if wake < sleep:
        return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_awake(sister_info, lead_name, state=None, config=None):
    if sister_info["name"] == lead_name:
        return True
    sc = _assign_today_schedule(sister_info["name"], state or {}, config or {})
    return _hour_in_range(now_aedt().hour, sc["wake"], sc["sleep"])

# ---------------- Rotation / Themes ----------------------------------------
def get_today_rotation(state, config):
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation(state, config):
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])
    log_event(f"[ROTATION] New index → {state['rotation_index']}")

def get_current_theme(state, config):
    today = today_aedt()
    if state.get("last_theme_update") is None or (today.weekday() == 0 and state.get("last_theme_update") != today):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
        log_event(f"[THEME] Switched to index {state['theme_index']} (AEDT Monday or first run)")
    return config["themes"][state.get("theme_index", 0)]

# ---------------- Family posting -------------------------------------------
async def post_to_family(message: str, sender, sisters, config):
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(message)
                    log_event(f"[POST] {sender}: {message}")
            except Exception as e:
                log_event(f"[ERROR] Send failed {sender}: {e}")
            break

# ---------------- Shared context (thread memory, outfit caps) --------------
def _ctx(state: dict) -> dict:
    cx = state.setdefault("channel_context", {})     # {channel_id: {last_speaker, last_reference, ts}}
    state.setdefault("last_spontaneous_ts", None)    # global timestamp for spontaneous jitter
    state.setdefault("outfit_posts_today", {})       # {"Aria": "YYYY-MM-DD", ...}
    return cx

def _update_channel_context(state: dict, channel_id: int, speaker: str, reference: str | None = None):
    cx = _ctx(state)
    cx[str(channel_id)] = {
        "last_speaker": speaker,
        "last_reference": reference or "",
        "ts": now_aedt().isoformat()
    }
    log_event(f"[CTX] #{channel_id} last_speaker={speaker} ref={reference or ''}")

# ---------------------------------------------------------------------------
# Persona wrapper: sibling vibe (+ “avoid books” bias for Aria in small talk)
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
    avoid_books_if_aria: bool = True,
):
    sister_cfg = next((s for s in config["rotation"] if s["name"] == sname), {})
    personality = sister_cfg.get("personality", "Neutral personality.")
    allow_swear = sister_cfg.get("swearing_allowed", False)

    mode_map = {
        "support":   "encouraging, warm, a little teasing if natural",
        "tease":     "poke fun, playful or bratty sibling energy (never cruel)",
        "challenge": "blunt or scolding like a strict sibling (short & pointed)",
        "story":     "tiny anecdote that sounds real (shared home memories, chores, food, media)",
        "default":   "casual sibling banter, natural and quick",
    }

    anti_book = ""
    if avoid_books_if_aria and sname == "Aria":
        anti_book = "Avoid defaulting to books; prefer present-moment, concrete things unless asked."

    mention_rule = "Only reference real siblings: Aria, Selene, Cassandra, Ivy, Will."
    addressing = f"If natural, address {address_to} directly. " if address_to else ""

    prompt = (
        f"You are {sname}. Personality: {personality}. "
        f"Tone role: {role}. Style mode: {mode_map.get(mode, 'casual sibling banter')}. "
        f"{'Mild swearing is okay if it fits.' if allow_swear else 'Do not swear.'} "
        f"{mention_rule} {anti_book} {addressing}{base_prompt}"
    )

    return await generate_llm_reply(
        sister=sname,
        user_message=prompt,
        theme=theme,
        role=role,
        history=history,
    )

# ---------------------------------------------------------------------------
# Rituals (AEDT)
# ---------------------------------------------------------------------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_morning", ["Morning."]))
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 siblingy sentences for morning. Start from: "{opener}" '
            f'Optionally mention a tiny specific thing you’re doing today (chores, food, plan).',
            theme, [], config, mode="story",
        )
    except Exception:
        lead_msg = opener

    wk = get_today_workout()
    if wk:
        lead_msg += f"\n\n🏋️ Today’s workout: {wk}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    # rotate after morning so next day’s lead changes
    advance_rotation(state, config)

async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    opener = random.choice(PERSONA_TONES.get(lead, {}).get("intro_night", ["Night."]))
    try:
        lead_msg = await _persona_reply(
            lead, "lead",
            f'Expand into 3–5 sentences for night reflection. Start from: "{opener}" '
            f'Keep it grounded and siblingy; one small real-feeling detail.',
            theme, [], config, mode="story",
        )
    except Exception:
        lead_msg = opener

    tomorrow = today_aedt() + timedelta(days=1)
    wk = get_today_workout(tomorrow)
    if wk:
        lead_msg += f"\n\n🌙 Tomorrow’s workout: {wk}"

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

# ---------------------------------------------------------------------------
# Outfit posts (capped to 1 per AEDT day per sibling)
# ---------------------------------------------------------------------------
async def generate_and_post_outfit(state, config, sisters, who: str):
    caps = state.setdefault("outfit_posts_today", {})
    today = str(today_aedt())
    if caps.get(who) == today:
        log_event(f"[OUTFIT] Skipped for {who} (already posted today)")
        return

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)

    # Very short outfit line; actual image gen handled elsewhere if present
    seasonal = random.choice(["spring", "summer", "autumn", "winter"])
    vibe_map = {
        "Aria": "soft layers, neat lines",
        "Selene": "cozy cardigan, relaxed slacks or long skirt",
        "Cassandra": "structured top, fitted pants, clean lines",
        "Ivy": "playful crop or graphic tee, skirt or cargos",
    }
    vibe = vibe_map.get(who, "casual, personality-aligned fit")

    msg = f"🧵 {who} — today’s fit: {vibe} ({seasonal})"
    await post_to_family(msg, sender=who, sisters=sisters, config=config)
    caps[who] = today
    log_event(f"[OUTFIT] Posted for {who}: {msg}")

# ---------------------------------------------------------------------------
# Spontaneous chat — jittered timing, thread-aware
# ---------------------------------------------------------------------------
async def send_spontaneous_task(state, config, sisters):
    last_ts = state.get("last_spontaneous_ts")
    if last_ts:
        mins = (now_aedt() - datetime.fromisoformat(last_ts)).total_seconds() / 60
        required = random.randint(42, 95)
        if mins < required:
            return

    rotation = get_today_rotation(state, config)
    lead = rotation["lead"]
    theme = get_current_theme(state, config)

    awake = [b.sister_info["name"] for b in sisters if is_awake(b.sister_info, lead, state, config)]
    if not awake:
        return

    # Choose speaker with anti-repeat weighting
    last_speaker = state.get("last_spontaneous_speaker")
    weights = [(0.35 if n == last_speaker else 1.0) for n in awake]
    speaker = random.choices(awake, weights=weights, k=1)[0]

    # Pick someone to address (feels like talking *to* someone)
    targets = [n for n in awake if n != speaker]
    address_to = random.choice(targets) if targets else None

    base = "Say one or two casual lines to spark sibling conversation. Keep it concrete."
    mode_bias = {
        "Aria": ["story", "support", "default"],
        "Selene": ["support", "story", "default"],
        "Cassandra": ["challenge", "tease", "default"],
        "Ivy": ["tease", "support", "default"],
    }
    mode = random.choice(mode_bias.get(speaker, ["default"]))

    try:
        msg = await _persona_reply(
            speaker, "support", base, theme, [], config, mode=mode, address_to=address_to
        )
    except Exception as e:
        log_event(f"[ERROR] Spontaneous gen failed for {speaker}: {e}")
        return

    if msg:
        await post_to_family(msg, sender=speaker, sisters=sisters, config=config)
        state["last_spontaneous_speaker"] = speaker
        state["last_spontaneous_ts"] = now_aedt().isoformat()
        log_event(f"[SPONT] {speaker} → {address_to or 'room'}: {msg}")

# ---------------------------------------------------------------------------
# Interactions — probabilistic, thread-aware, natural endings
# ---------------------------------------------------------------------------
async def handle_sister_message(state, config, sisters, author, content, channel_id):
    if author not in SIBLING_NAMES:
        # user talking — siblings may still reply elsewhere in the system
        pass

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    # Update channel short-term memory
    _update_channel_context(state, channel_id, author, reference=content[:80])

    # Try to keep replies focused on the latest speaker in the channel
    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author:
            continue
        if not is_awake(bot.sister_info, lead, state, config):
            continue

        # Force reply if directly mentioned
        lower = content.lower()
        force = (sname.lower() in lower) or ("everyone" in lower)

        # Base chances by role
        chance = 0.22
        if sname == lead:
            chance = 0.75
        elif sname in rotation["supports"]:
            chance = 0.48
        elif sname == rotation["rest"]:
            chance = 0.18

        # Thread targeting: prefer replying to the most recent speaker
        ch_ctx = state["channel_context"].get(str(channel_id), {})
        if ch_ctx.get("last_speaker") == author:
            chance += 0.18  # nudge to keep the back-and-forth

        if force:
            chance = 1.0

        if random.random() < max(0.05, min(1.0, chance)):
            mode = random.choice(["tease", "support", "challenge", "default", "story"])
            try:
                reply = await _persona_reply(
                    sname, "support",
                    f'Reply directly to {author} who said: "{content}". 1–2 siblingy sentences; keep it concrete. '
                    f'End naturally if it feels done.',
                    theme, [], config, mode=mode, address_to=author
                )
            except Exception as e:
                log_event(f"[ERROR] Reply gen failed for {sname}: {e}")
                continue

            if reply:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                # 35% chance to allow author one follow-up, then stop
                if random.random() < 0.35:
                    await asyncio.sleep(random.randint(3, 9))
                    try:
                        follow = await _persona_reply(
                            author, "support",
                            f"One short follow-up to {sname}. If it feels complete, close it softly.",
                            theme, [], config,
                            mode=random.choice(["tease", "support", "default"]),
                            address_to=sname
                        )
                        if follow:
                            await post_to_family(follow, sender=author, sisters=sisters, config=config)
                    except Exception as e:
                        log_event(f"[ERROR] Follow-up gen failed for {author}: {e}")
