import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

PERSO_PATH = "/Autonomy/personalities/Cassandra_Personality.json"
MEMO_PATH  = "/Autonomy/memory/Cassandra_Memory.json"

AEDT = pytz.timezone("Australia/Sydney")

CASS_MIN_SLEEP = 40 * 60
CASS_MAX_SLEEP = 95 * 60

# Cass: prim & proper but (openly) a bit of a gym rat
CASS_MEDIA = {
    "fitness": ["push-pull-legs logs", "deadlift PR clips", "yoga mobility routines"],
    "shows":   ["House", "Suits"],
    "music":   ["rock workout playlists", "metal for lifting"],
    "games":   ["Hades", "Elden Ring"],
}

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[Cassandra][WARN] JSON read failed {path}: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[Cassandra][WARN] JSON write failed {path}: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSO_PATH, {})
    d.setdefault("name", "Cassandra")
    d.setdefault("likes", ["neatness", "results", "efficiency", "strength training"])
    d.setdefault("dislikes", ["sloppiness"])
    d.setdefault("style", ["firm", "precise", "protective"])
    d.setdefault("core_personality", "Blunt but fair; high standards; openly loves gym progress.")
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
    key, kd = "Cassandra_schedule", "Cassandra_schedule_date"
    today = datetime.now(AEDT).date()
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Cassandra", {"wake": [6, 8], "sleep": [22, 23]})
    sched = {"wake": _pick_inclusive(scfg.get("wake", [6, 8])), "sleep": _pick_inclusive(scfg.get("sleep", [22, 23]))}
    state[key] = sched; state[kd] = today; return sched

def _hour_in_range(h, w, s): 
    if w == s: return True
    if w < s:  return w <= h < s
    return h >= w or h < s

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now(AEDT).hour, sc["wake"], sc["sleep"])

def _progress_phrase(p: float) -> str:
    if p >= 1.0: return random.choice(["Done. Good. Next."])
    if p >= 0.7: return random.choice(["Almost there—don’t coast."])
    if p >= 0.4: return random.choice(["Midway. Keep the tempo."])
    return random.choice(["Start is fine; commit to the next step."])

def _media_hits(text: str, likes: List[str]) -> float:
    lower = text.lower(); liked = " ".join(likes).lower()
    score = 0.0
    for cat in CASS_MEDIA.values():
        for m in cat:
            if m.lower() in lower:
                score += 0.25
                if any(t in liked for t in m.lower().split()):
                    score += 0.15
    return score

async def _persona_reply(base_prompt: str, strict=False, progress: Optional[float]=None) -> str:
    pr = load_profile()
    tone = "firm, concise, a little protective" if strict else "precise but warm"
    proj = ""
    if progress is not None:
        proj = " " + _progress_phrase(progress)
    prompt = (
        f"You are Cassandra. Personality: {pr.get('core_personality')}. "
        f"Style: {', '.join(pr.get('style', []))}. Speak {tone}.{proj} {base_prompt}"
    )
    return await generate_llm_reply("Cassandra", prompt, None, "sister", [])

async def _post(state, config, sisters, text):
    for bot in sisters:
        if bot.sister_info["name"] == "Cassandra" and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch: await ch.send(text); log_event(f"[Cassandra] {text}")
            break

async def _chatter_loop(state, config, sisters):
    if state.get("cass_chatter_started"): return
    state["cass_chatter_started"] = True
    while True:
        try:
            if is_online(state, config) and random.random() < 0.11:
                mem = load_memory()
                prog = mem.get("projects", {}).get("Personal task", {}).get("progress", random.random())
                msg = await _persona_reply("One line that nudges action without coddling.", strict=random.random()<0.6, progress=prog)
                if msg: await _post(state, config, sisters, msg)
        except Exception as e:
            log_event(f"[Cassandra][ERROR] chatter: {e}")
        await asyncio.sleep(random.randint(CASS_MIN_SLEEP, CASS_MAX_SLEEP))

async def cass_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    pr = load_profile()
    chance = 0.22 + _media_hits(content, pr.get("likes", []))
    if "cassandra" in content.lower(): chance = 1.0
    if random.random() > min(1.0, max(0.05, chance)): return
    mem = load_memory()
    prog = mem.get("projects", {}).get("Personal task", {}).get("progress", None)
    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply like a blunt but caring sister (1–2 lines).',
            strict=random.random() < 0.7, progress=prog
        )
        if reply: await _post(state, config, sisters, reply)
    except Exception as e:
        log_event(f"[Cassandra][ERROR] reactive: {e}")

def ensure_cass_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("cass_chatter_started"):
        asyncio.create_task(_chatter_loop(state, config, sisters))
