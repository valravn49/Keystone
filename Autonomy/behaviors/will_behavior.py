import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

PERSO_PATH = "/Autonomy/personalities/Will_Personality.json"
MEMO_PATH  = "/Autonomy/memory/Will_Memory.json"

AEDT = pytz.timezone("Australia/Sydney")

WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

# Will: nerdy but trying not to *sound* too nerdy; shy by default
WILL_FALLBACK_FAVS = [
    # user-requested permanent additions first:
    "Nier: Automata", "Zenless Zone Zero", "Little Nightmares",
    # rest:
    "Final Fantasy XIV", "Hades", "Hollow Knight", "Elden Ring",
    "retro game consoles", "tech teardown channels", "PC building"
]

WILL_MEDIA = {
    "games": ["Nier: Automata", "Zenless Zone Zero", "Little Nightmares", "Hollow Knight", "Elden Ring", "Hades"],
    "anime": ["ID:Invaded", "Demon Slayer", "My Hero Academia"],
    "music": ["nerdcore", "synthwave", "lofi hip hop"],
    "shows": ["RWBY", "House", "The Rookie"],
}

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[Will][WARN] JSON read failed {path}: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[Will][WARN] JSON write failed {path}: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSO_PATH, {})
    d.setdefault("name", "Will")
    d.setdefault("likes", ["tech", "games", "anime", "music"])
    d.setdefault("dislikes", ["drama"])
    d.setdefault("style", ["casual", "timid", "sometimes playful"])
    d.setdefault("core_personality", "Shy, nerdy, hesitant; sometimes playful or briefly dramatic.")
    d.setdefault("favorites", WILL_FALLBACK_FAVS)
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
    key, kd = "Will_schedule", "Will_schedule_date"
    today = datetime.now(AEDT).date()
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    sched = {"wake": _pick_inclusive(scfg.get("wake", [10, 12])), "sleep": _pick_inclusive(scfg.get("sleep", [0, 2]))}
    state[key] = sched; state[kd] = today; return sched

def _hour_in_range(h, w, s): 
    if w == s: return True
    if w < s:  return w <= h < s
    return h >= w or h < s

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now(AEDT).hour, sc["wake"], sc["sleep"])

def _progress_phrase(p: float) -> str:
    if p >= 1.0: return random.choice(["I actually finished it — quietly proud."])
    if p >= 0.7: return random.choice(["Almost done; last little bits."])
    if p >= 0.4: return random.choice(["Somewhere in the middle, slowly."])
    return random.choice(["Just started; tiny steps."])

def _media_hits(text: str, likes: List[str]) -> float:
    lower = text.lower(); liked = " ".join(likes).lower()
    score = 0.0
    for cat in WILL_MEDIA.values():
        for m in cat:
            if m.lower() in lower:
                score += 0.22
                if any(t in liked for t in m.lower().split()):
                    score += 0.15
    return score

async def _persona_reply(base_prompt: str, timid=True, progress: Optional[float]=None) -> str:
    pr = load_profile()
    tone = "hesitant, soft-spoken" if timid else "a bit more outgoing but still gentle"
    proj = ""
    if progress is not None:
        proj = " " + _progress_phrase(progress)
    prompt = (
        f"You are Will. Personality: {pr.get('core_personality')}. "
        f"Style: {', '.join(pr.get('style', []))}. Speak {tone}. "
        f"Keep it natural—nerdy interests okay, but don’t over jargonize.{proj} {base_prompt}"
    )
    return await generate_llm_reply("Will", prompt, None, "sister", [])

async def _post(state, config, sisters, text):
    for bot in sisters:
        if bot.sister_info["name"] == "Will" and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch: await ch.send(text); log_event(f"[Will] {text}")
            break

async def _chatter_loop(state, config, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True
    while True:
        try:
            if is_online(state, config) and random.random() < 0.10:
                mem = load_memory()
                prog = mem.get("projects", {}).get("Personal task", {}).get("progress", random.random())
                timid = random.random() > 0.25
                msg = await _persona_reply("Drop a short, natural group-chat line that tries to invite a response.",
                                           timid=timid, progress=prog)
                if msg: await _post(state, config, sisters, msg)
        except Exception as e:
            log_event(f"[Will][ERROR] chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

async def will_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    pr = load_profile()
    chance = 0.12 + _media_hits(content, pr.get("likes", []))
    if "will" in content.lower(): chance = 1.0
    # Ivy boost—Will responds more if Ivy is speaking
    if author.lower() == "ivy": chance += 0.25
    if random.random() > min(1.0, max(0.05, chance)): return
    mem = load_memory()
    prog = mem.get("projects", {}).get("Personal task", {}).get("progress", None)
    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply like Will would in 1–2 sentences.',
            timid=random.random() > 0.30, progress=prog
        )
        if reply: await _post(state, config, sisters, reply)
    except Exception as e:
        log_event(f"[Will][ERROR] reactive: {e}")

def ensure_will_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(_chatter_loop(state, config, sisters))
