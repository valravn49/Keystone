import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

# ---------- Paths ----------
PERSONALITY_JSON = "/Autonomy/personalities/Aria_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Aria_Memory.json"

# ---------- Timezone ----------
AEDT = pytz.timezone("Australia/Sydney")

# ---------- Pacing ----------
MIN_SLEEP = 50 * 60
MAX_SLEEP = 120 * 60

# ---------- Tone/weights ----------
THOUGHTFUL_CHANCE = 0.30
MEDIA_MENTION_BASE = 0.18  # light media flavor only

# ---------- JSON helpers ----------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Aria JSON read failed {path}: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Aria JSON write failed {path}: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSONALITY_JSON, {})
    d.setdefault("style", ["structured", "gentle", "reflective"])
    d.setdefault("likes", [])
    d.setdefault("dislikes", [])
    d.setdefault("media", {})
    return d

def load_memory() -> Dict:
    d = _load_json(MEMORY_JSON, {"projects": {}, "recent_notes": []})
    d.setdefault("projects", {})
    d.setdefault("recent_notes", [])
    return d

def save_memory(mem: Dict):
    _save_json(MEMORY_JSON, mem)

# ---------- Schedule / Awake ----------
def _pick_hour(span: List[int]) -> int:
    lo, hi = int(span[0]), int(span[1])
    if hi < lo:
        lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key, kd = "aria_schedule", "aria_schedule_date"
    if state.get(kd) == today and key in state:
        return state[key]
    c = (config.get("schedules", {}) or {}).get("Aria", {"wake":[6,8], "sleep":[22,23]})
    schedule = {"wake": _pick_hour(c.get("wake",[6,8])), "sleep": _pick_hour(c.get("sleep",[22,23]))}
    state[key], state[kd] = schedule, today
    return schedule

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep: return True
    if wake < sleep:  return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------- Small helpers ----------
def _media_pool_from_profile(profile: Dict) -> List[str]:
    media = profile.get("media", {})
    out = []
    for v in media.values():
        if isinstance(v, list): out.extend(v)
    return out

def _media_mentions_in(text: str, pool: List[str]) -> List[str]:
    t = text.lower()
    hits = []
    for m in pool:
        if m.lower() in t:
            hits.append(m)
    return list(set(hits))

def _post_to_family(msg: str, sisters, config: Dict, who="Aria"):
    for bot in sisters:
        if bot.sister_info["name"] == who and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                return asyncio.create_task(ch.send(msg))

# ---------- Persona reply ----------
async def _persona_reply(base_prompt: str, thoughtful: bool, project_progress: Optional[float]) -> str:
    profile = load_profile()
    style = ", ".join(profile.get("style", ["structured", "gentle"]))
    tone = "quietly thoughtful and deliberate" if thoughtful else "soft, concise, lightly teasing (dry wit allowed)"
    proj = ""
    if project_progress is not None:
        if project_progress < 0.4:
            proj = " Your project is still early; you’re sketching plans and tidying inputs."
        elif project_progress < 0.8:
            proj = " It’s mid-way and steady — small corrections, precise notes."
        else:
            proj = " Almost done; you keep refining edges and alignment."
    prompt = (
        f"You are Aria. Style: {style}. Speak with {tone}. Avoid rambling; prefer clear, grounded lines."
        f"{proj} {base_prompt}"
    )
    return await generate_llm_reply(
        sister="Aria", user_message=prompt, theme=None, role="sister", history=[]
    )

# ---------- Chatter loop ----------
async def aria_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("aria_chatter_started"): return
    state["aria_chatter_started"] = True
    while True:
        if is_online(state, config) and random.random() < 0.08:
            try:
                msg = await _persona_reply(
                    "Share one calm observation or small plan for the day.",
                    thoughtful=(random.random() < THOUGHTFUL_CHANCE),
                    project_progress=state.get("Aria_project_progress", random.random()),
                )
                if msg: _post_to_family(msg, sisters, config, "Aria"); log_event(f"[CHATTER] Aria: {msg}")
            except Exception as e:
                log_event(f"[ERROR] Aria chatter: {e}")
        await asyncio.sleep(random.randint(MIN_SLEEP, MAX_SLEEP))

# ---------- Reactive handler ----------
async def aria_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_online(state, config): return
    profile = load_profile()

    # Base chance + small boost if content touches Aria's interests/media
    base = 0.18
    likes = profile.get("likes", [])
    if any(k.lower() in content.lower() for k in likes): base += 0.12

    media_pool = _media_pool_from_profile(profile)
    media_hits = _media_mentions_in(content, media_pool)
    if media_hits: base += 0.10

    if "aria" in content.lower(): base = 1.0
    if random.random() >= min(0.95, base): return

    # Gentle stagger
    await asyncio.sleep(random.randint(3, 10))

    # Light media weaving: only sometimes, keep it subtle
    media_hint = ""
    if media_hits and random.random() < MEDIA_MENTION_BASE:
        media_hint = f" If natural, reference {random.choice(media_hits)} very briefly."

    msg = await _persona_reply(
        f'{author} said: "{content}". Respond naturally as a calm, meticulous older sister.{media_hint} '
        f"Prefer practical, present-moment comments over book references.",
        thoughtful=(random.random() < 0.5),
        project_progress=state.get("Aria_project_progress", random.random()),
    )
    if msg:
        _post_to_family(msg, sisters, config, "Aria")
        log_event(f"[REPLY] Aria → {author}: {msg}")

# ---------- Startup ----------
def ensure_aria_systems(state: Dict, config: Dict, sisters):
    assign_schedule(state, config)
    if not state.get("aria_chatter_started"):
        asyncio.create_task(aria_chatter_loop(state, config, sisters))
