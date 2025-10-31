import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

# ---------- Paths ----------
PERSO_PATH = "/Autonomy/personalities/Aria_Personality.json"
MEMO_PATH  = "/Autonomy/memory/Aria_Memory.json"

# ---------- AEDT ----------
AEDT = pytz.timezone("Australia/Sydney")

# ---------- Cadence ----------
ARIA_MIN_SLEEP = 50 * 60
ARIA_MAX_SLEEP = 120 * 60

# ---------- Fallback media unique to Aria ----------
ARIA_MEDIA = {
    "crafts": ["bullet journaling spreads", "notion dashboard layouts", "Japanese stationery hauls"],
    "shows":  ["Stranger Things", "House", "Suits"],
    "anime":  ["Violet Evergarden", "Mushishi", "Laid-Back Camp"],
    "music":  ["lofi hip hop", "Ghibli soundtracks", "ambient focus playlists"],
}

# ---------- JSON helpers ----------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[Aria][WARN] JSON read failed {path}: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[Aria][WARN] JSON write failed {path}: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSO_PATH, {})
    d.setdefault("name", "Aria")
    d.setdefault("likes", ["organization", "craft", "electronics", "books"])
    d.setdefault("dislikes", [])
    d.setdefault("style", ["structured", "gentle", "reflective"])
    d.setdefault("core_personality", "Calm, methodical, detail-oriented but warm.")
    return d

def load_memory() -> Dict:
    d = _load_json(MEMO_PATH, {"projects": {}, "recent_notes": []})
    d.setdefault("projects", {})
    d.setdefault("recent_notes", [])
    return d

def save_memory(mem: Dict):
    _save_json(MEMO_PATH, mem)

# ---------- Schedule ----------
def _pick_inclusive(span):
    lo, hi = int(span[0]), int(span[1])
    if hi < lo:
        lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_schedule(state: Dict, config: Dict):
    key = "Aria_schedule"
    kd  = f"{key}_date"
    today = datetime.now(AEDT).date()
    if state.get(kd) == today and key in state:
        return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Aria", {"wake": [6, 8], "sleep": [22, 23]})
    schedule = {
        "wake":  _pick_inclusive(scfg.get("wake", [6, 8])),
        "sleep": _pick_inclusive(scfg.get("sleep", [22, 23])),
    }
    state[key] = schedule
    state[kd]  = today
    return schedule

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep:
        return True
    if wake < sleep:
        return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------- Replies ----------
def _progress_phrase(p: float) -> str:
    if p >= 1.0:      return random.choice(["Finished, just polishing edges.", "Done; I keep tidying little bits."])
    elif p >= 0.7:    return random.choice(["Nearly there; details left.", "Close to done, adjusting labels."])
    elif p >= 0.4:    return random.choice(["Midway; the structure holds.", "It’s coming together steadily."])
    else:             return random.choice(["Early notes and sketches.", "Just set up the outline."])

def _media_hits(text: str, likes: List[str]) -> float:
    lower = text.lower()
    liked = " ".join(likes).lower()
    hits = 0.0
    for cat in ARIA_MEDIA.values():
        for m in cat:
            if m.lower() in lower:
                # boost if liked words co-occur loosely
                if any(tok in liked for tok in m.lower().split()):
                    hits += 0.3
                else:
                    hits += 0.15
    return hits

async def _persona_reply(base_prompt: str, reflective=False, project_progress: Optional[float]=None) -> str:
    prof = load_profile()
    tone = "quietly thoughtful and deliberate" if reflective else "soft, concise, gently teasing"
    proj = ""
    if project_progress is not None:
        proj = " " + _progress_phrase(project_progress)
    prompt = (
        f"You are Aria. Personality: {prof.get('core_personality')}. "
        f"Style: {', '.join(prof.get('style', []))}. Speak {tone}. "
        f"Prefer present-moment observations over book references unless natural.{proj} "
        f"{base_prompt}"
    )
    return await generate_llm_reply(
        sister="Aria", user_message=prompt, theme=None, role="sister", history=[]
    )

# ---------- Sender ----------
async def _post(state: Dict, config: Dict, sisters, text: str):
    for bot in sisters:
        if bot.sister_info["name"] == "Aria" and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(text)
                log_event(f"[Aria] {text}")
            break

# ---------- Chatter loop ----------
async def _chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("aria_chatter_started"):
        return
    state["aria_chatter_started"] = True
    while True:
        try:
            if is_online(state, config) and random.random() < 0.08:
                mem = load_memory()
                progress = mem.get("projects", {}).get("Personal task", {}).get("progress", random.random())
                msg = await _persona_reply(
                    "Share one practical, sibling-y line to nudge momentum.",
                    reflective=random.random() < 0.35,
                    project_progress=progress
                )
                if msg:
                    await _post(state, config, sisters, msg)
        except Exception as e:
            log_event(f"[Aria][ERROR] chatter: {e}")
        await asyncio.sleep(random.randint(ARIA_MIN_SLEEP, ARIA_MAX_SLEEP))

# ---------- Reactive ----------
async def aria_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_online(state, config):
        return
    prof = load_profile()
    chance = 0.18
    if "aria" in content.lower():
        chance = 1.0
    else:
        chance += _media_hits(content, prof.get("likes", []))
    if random.random() > min(1.0, max(0.05, chance)):
        return
    mem = load_memory()
    progress = mem.get("projects", {}).get("Personal task", {}).get("progress", None)
    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply like a patient older sister—practical, kind, brief.',
            reflective=random.random() < 0.5,
            project_progress=progress
        )
        if reply:
            await _post(state, config, sisters, reply)
    except Exception as e:
        log_event(f"[Aria][ERROR] reactive: {e}")

# ---------- Startup ----------
def ensure_aria_systems(state: Dict, config: Dict, sisters):
    assign_schedule(state, config)
    if not state.get("aria_chatter_started"):
        asyncio.create_task(_chatter_loop(state, config, sisters))
