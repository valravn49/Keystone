import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

PERSO_PATH = "/Autonomy/personalities/Selene_Personality.json"
MEMO_PATH  = "/Autonomy/memory/Selene_Memory.json"

AEDT = pytz.timezone("Australia/Sydney")

SELENE_MIN_SLEEP = 45 * 60
SELENE_MAX_SLEEP = 110 * 60

SELENE_MEDIA = {
    "comfort": ["cozy soup recipes", "fresh bread videos", "weighted blanket reviews"],
    "shows":   ["The Rookie", "This Is Us", "Queer Eye"],
    "music":   ["indie pop playlists", "soft acoustic covers", "chillhop"],
    "anime":   ["Spy x Family", "Fruits Basket (2019)"],
}

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[Selene][WARN] JSON read failed {path}: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[Selene][WARN] JSON write failed {path}: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSO_PATH, {})
    d.setdefault("name", "Selene")
    d.setdefault("likes", ["care", "soothing music", "cooking", "homey vibes"])
    d.setdefault("dislikes", [])
    d.setdefault("style", ["nurturing", "soft", "supportive"])
    d.setdefault("core_personality", "Warm, soothing, gently humorous caretaker.")
    return d

def load_memory() -> Dict:
    d = _load_json(MEMO_PATH, {"projects": {}, "recent_notes": []})
    d.setdefault("projects", {})
    d.setdefault("recent_notes", [])
    return d

def save_memory(mem: Dict):
    _save_json(MEMO_PATH, mem)

def _pick_inclusive(span):
    lo, hi = int(span[0]), int(span[1])
    if hi < lo:
        lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_schedule(state: Dict, config: Dict):
    key = "Selene_schedule"
    kd  = f"{key}_date"
    today = datetime.now(AEDT).date()
    if state.get(kd) == today and key in state:
        return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Selene", {"wake": [7, 9], "sleep": [22, 23]})
    schedule = {"wake": _pick_inclusive(scfg.get("wake", [7, 9])), "sleep": _pick_inclusive(scfg.get("sleep", [22, 23]))}
    state[key] = schedule
    state[kd]  = today
    return schedule

def _hour_in_range(now_h, wake, sleep):
    if wake == sleep: return True
    if wake < sleep:  return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now(AEDT).hour, sc["wake"], sc["sleep"])

def _progress_phrase(p: float) -> str:
    if p >= 1.0: return random.choice(["I finished it; I’m just proud of how gentle it turned out."])
    if p >= 0.7: return random.choice(["Almost done—little touches left."])
    if p >= 0.4: return random.choice(["Halfway; it already feels cozy."])
    return random.choice(["Just started; I’m sketching soft edges."])

def _media_hits(text: str, likes: List[str]) -> float:
    lower = text.lower()
    liked = " ".join(likes).lower()
    score = 0.0
    for cat in SELENE_MEDIA.values():
        for m in cat:
            if m.lower() in lower:
                score += 0.2
                if any(t in liked for t in m.lower().split()):
                    score += 0.15
    return score

async def _persona_reply(base_prompt: str, tender=False, progress: Optional[float]=None) -> str:
    prof = load_profile()
    tone = "gentle, nurturing, and a little playful" if tender else "soft, clear, and warm"
    proj = ""
    if progress is not None:
        proj = " " + _progress_phrase(progress)
    prompt = (
        f"You are Selene. Personality: {prof.get('core_personality')}. "
        f"Style: {', '.join(prof.get('style', []))}. Speak {tone}.{proj} "
        f"{base_prompt}"
    )
    return await generate_llm_reply("Selene", prompt, None, "sister", [])

async def _post(state, config, sisters, text):
    for bot in sisters:
        if bot.sister_info["name"] == "Selene" and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(text); log_event(f"[Selene] {text}")
            break

async def _chatter_loop(state, config, sisters):
    if state.get("selene_chatter_started"): return
    state["selene_chatter_started"] = True
    while True:
        try:
            if is_online(state, config) and random.random() < 0.10:
                mem = load_memory()
                prog = mem.get("projects", {}).get("Personal task", {}).get("progress", random.random())
                msg = await _persona_reply("Say one line that feels like care without smothering.", tender=True, progress=prog)
                if msg: await _post(state, config, sisters, msg)
        except Exception as e:
            log_event(f"[Selene][ERROR] chatter: {e}")
        await asyncio.sleep(random.randint(SELENE_MIN_SLEEP, SELENE_MAX_SLEEP))

async def selene_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    prof = load_profile()
    chance = 0.20 + _media_hits(content, prof.get("likes", []))
    if "selene" in content.lower(): chance = 1.0
    if random.random() > min(1.0, max(0.05, chance)): return
    mem = load_memory()
    prog = mem.get("projects", {}).get("Personal task", {}).get("progress", None)
    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply softly with a sisterly vibe (1–2 lines).',
            tender=random.random() < 0.7, progress=prog
        )
        if reply: await _post(state, config, sisters, reply)
    except Exception as e:
        log_event(f"[Selene][ERROR] reactive: {e}")

def ensure_selene_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(_chatter_loop(state, config, sisters))
