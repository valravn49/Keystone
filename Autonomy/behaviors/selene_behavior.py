import os, json, random, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List

from llm import generate_llm_reply
from logger import log_event

AEDT = ZoneInfo("Australia/Sydney")

PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Selene_Memory.json"

SELENE_MIN_SLEEP = 45 * 60
SELENE_MAX_SLEEP = 110 * 60

REAL_MEDIA = {
    "games": [
        "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
        "Stardew Valley", "Hollow Knight", "NieR:Automata", "Zenless Zone Zero"
    ],
    "anime": [
        "Demon Slayer", "My Hero Academia", "ID:Invaded", "Kabaneri of the Iron Fortress"
    ],
    "shows": [
        "RWBY", "House", "The Rookie", "Suits"
    ],
    "music": [
        "lofi hip hop", "indie pop playlists", "synthwave",
        "BABYMETAL", "Ghost", "Jonathan Young", "Ninja Sex Party", "nerdcore"
    ],
}

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Selene JSON read failed {path}: {e}")
    return default

def load_profile() -> Dict:
    d = _load_json(PERSONALITY_JSON, {})
    d.setdefault("likes", ["cozy cooking", "care routines", "soft playlists", "true crime podcasts"])
    d.setdefault("dislikes", ["cold rooms", "skipped meals"])
    d.setdefault("style", ["warm", "affectionate", "playful"])
    return d

def load_memory() -> Dict:
    d = _load_json(MEMORY_JSON, {"projects": {}, "recent_notes": []})
    d.setdefault("projects", {}); d.setdefault("recent_notes", [])
    return d

def save_memory(d: Dict):
    try:
        os.makedirs(os.path.dirname(MEMORY_JSON), exist_ok=True)
        with open(MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Selene memory write failed: {e}")

def assign_schedule(state: Dict, config: Dict):
    today = datetime.now(tz=AEDT).date()
    key = "selene_schedule"; kd = f"{key}_date"
    if state.get(kd) == today and key in state: return state[key]
    sch = (config.get("schedules", {}) or {}).get("Selene", {"wake": [7, 9], "sleep": [23, 24]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        if hi < lo: lo, hi = hi, lo
        return random.randint(lo, hi)
    schedule = {"wake": pick(sch["wake"]), "sleep": pick(sch["sleep"])}
    state[key] = schedule; state[kd] = today
    return schedule

def _hour_in_range(n, w, s):
    if w == s: return True
    if w < s:  return w <= n < s
    return n >= w or n < s

def is_online(state, config):
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now(tz=AEDT).hour, sc["wake"], sc["sleep"])

def _hits(text: str) -> List[str]:
    low = text.lower(); out=[]
    for items in REAL_MEDIA.values():
        for it in items:
            if it.lower() in low: out.append(it)
    return list(set(out))

def _weight(text: str, profile: Dict) -> float:
    likes = " ".join(profile.get("likes", [])).lower()
    dislikes = " ".join(profile.get("dislikes", [])).lower()
    boost = 0.0
    for m in _hits(text):
        mlow = m.lower()
        if any(w in likes for w in mlow.split()):    boost += 0.25
        if any(w in dislikes for w in mlow.split()): boost -= 0.20
    return boost

async def _persona_reply(base: str) -> str:
    p = load_profile()
    style = ", ".join(p.get("style", ["warm", "affectionate"]))
    prompt = (
        f"You are Selene. Personality: tender, playful, comfort-first. "
        f"Speak with a {style} tone; sound like the cuddly sibling who fusses kindly. "
        f"Be a little flirty but wholesome. Keep it short and real. {base}"
    )
    return await generate_llm_reply("Selene", prompt, None, "sister", [])

async def chatter_loop(state, config, sisters):
    if state.get("selene_chatter_started"): return
    state["selene_chatter_started"] = True
    while True:
        if is_online(state, config) and random.random() < 0.1:
            try:
                msg = await _persona_reply(
                    "Check in with the family about small comforts (snacks, water, blanket), "
                    "and tease someone gently by name if it fits."
                )
                if msg:
                    for bot in sisters:
                        if bot.is_ready() and bot.sister_info["name"] == "Selene":
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch: await ch.send(msg); log_event(f"[Selene][chatter] {msg}")
            except Exception as e:
                log_event(f"[ERROR] Selene chatter: {e}")
        await asyncio.sleep(random.randint(SELENE_MIN_SLEEP, SELENE_MAX_SLEEP))

async def handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    prof = load_profile()
    chance = 0.2 + _weight(content, prof)
    if "selene" in content.lower(): chance = 1.0
    if random.random() >= min(1.0, max(0.05, chance)) and "selene" not in content.lower():
        return
    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — answer affectionately with sibling playfulness. "
            f"Offer a tiny comfort suggestion or warm praise if it fits."
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Selene":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch: await ch.send(reply); log_event(f"[Selene][reply] → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Selene reply: {e}")

def ensure_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(chatter_loop(state, config, sisters))
