import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

PERSO_PATH = "/Autonomy/personalities/Ivy_Personality.json"
MEMO_PATH  = "/Autonomy/memory/Ivy_Memory.json"

AEDT = pytz.timezone("Australia/Sydney")

IVY_MIN_SLEEP = 35 * 60
IVY_MAX_SLEEP = 90 * 60

# Ivy: fashionista + open grease-monkey interest
IVY_MEDIA = {
    "fashion": ["thrift flips", "runway micro trends", "capsule wardrobes"],
    "mechanic": ["engine rebuild timelapses", "detailing videos", "track day vlogs"],
    "music":   ["nerdcore drops", "hyperpop", "rock remixes"],
    "anime":   ["Kabaneri of the Iron Fortress", "ID:Invaded", "Jujutsu Kaisen"],
    "games":   ["Zenless Zone Zero", "Code Vein", "Overwatch 2"],
    "shows":   ["RWBY", "The Rookie"],
}

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[Ivy][WARN] JSON read failed {path}: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[Ivy][WARN] JSON write failed {path}: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSO_PATH, {})
    d.setdefault("name", "Ivy")
    d.setdefault("likes", ["fashion", "teasing", "play", "engines"])
    d.setdefault("dislikes", [])
    d.setdefault("style", ["bratty", "sparkly", "affectionate"])
    d.setdefault("core_personality", "Playful, bratty, affectionate; quick teasing, quick to help.")
    return d

def load_memory() -> Dict:
    d = _load_json(MEMO_PATH, {"projects": {}, "recent_notes": []})
    d.setdefault("projects", {})
    d.setdefault("recent_notes", [])
    return d

def save_memory(mem: Dict): _save_json(MEMO_PATH, mem)

def _pick_inclusive(span):
    lo, hi = int(span[0]), int(span[1])
    if hi < lo: lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_schedule(state: Dict, config: Dict):
    key, kd = "Ivy_schedule", "Ivy_schedule_date"
    today = datetime.now(AEDT).date()
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Ivy", {"wake": [8, 10], "sleep": [23, 1]})
    sched = {"wake": _pick_inclusive(scfg.get("wake", [8, 10])), "sleep": _pick_inclusive(scfg.get("sleep", [23, 1]))}
    state[key] = sched; state[kd] = today; return sched

def _hour_in_range(h, w, s): 
    if w == s: return True
    if w < s:  return w <= h < s
    return h >= w or h < s

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now(AEDT).hour, sc["wake"], sc["sleep"])

def _progress_phrase(p: float) -> str:
    if p >= 1.0: return random.choice(["Done~ I look cute *and* the bolts are tight."])
    if p >= 0.7: return random.choice(["Nearly there — one last tweak."])
    if p >= 0.4: return random.choice(["Halfway — messy hands, big grin."])
    return random.choice(["I just started, don’t rush me~"])

def _media_hits(text: str, likes: List[str]) -> float:
    lower = text.lower(); liked = " ".join(likes).lower()
    score = 0.0
    for cat in IVY_MEDIA.values():
        for m in cat:
            if m.lower() in lower:
                score += 0.25
                if any(t in liked for t in m.lower().split()):
                    score += 0.15
    return score

async def _persona_reply(base_prompt: str, bratty=False, progress: Optional[float]=None) -> str:
    pr = load_profile()
    tone = "teasing, sparkly, affectionate" if bratty else "playful, warm"
    proj = ""
    if progress is not None:
        proj = " " + _progress_phrase(progress)
    prompt = (
        f"You are Ivy. Personality: {pr.get('core_personality')}. "
        f"Style: {', '.join(pr.get('style', []))}. Speak {tone}.{proj} {base_prompt}"
    )
    return await generate_llm_reply("Ivy", prompt, None, "sister", [])

async def _post(state, config, sisters, text):
    for bot in sisters:
        if bot.sister_info["name"] == "Ivy" and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch: await ch.send(text); log_event(f"[Ivy] {text}")
            break

async def _chatter_loop(state, config, sisters):
    if state.get("ivy_chatter_started"): return
    state["ivy_chatter_started"] = True
    while True:
        try:
            if is_online(state, config) and random.random() < 0.14:
                mem = load_memory()
                prog = mem.get("projects", {}).get("Personal task", {}).get("progress", random.random())
                msg = await _persona_reply("One line of playful sibling energy—call someone out (kindly).", bratty=random.random() < 0.7, progress=prog)
                if msg: await _post(state, config, sisters, msg)
        except Exception as e:
            log_event(f"[Ivy][ERROR] chatter: {e}")
        await asyncio.sleep(random.randint(IVY_MIN_SLEEP, IVY_MAX_SLEEP))

async def ivy_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    pr = load_profile()
    chance = 0.24 + _media_hits(content, pr.get("likes", []))
    if "ivy" in content.lower(): chance = 1.0
    if random.random() > min(1.0, max(0.05, chance)): return
    mem = load_memory()
    prog = mem.get("projects", {}).get("Personal task", {}).get("progress", None)
    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Respond bratty-cute (1–2 lines), affectionate under it.',
            bratty=random.random() < 0.75, progress=prog
        )
        if reply: await _post(state, config, sisters, reply)
    except Exception as e:
        log_event(f"[Ivy][ERROR] reactive: {e}")

def ensure_ivy_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(_chatter_loop(state, config, sisters))
