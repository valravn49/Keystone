import os, json, random, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List

from llm import generate_llm_reply
from logger import log_event

AEDT = ZoneInfo("Australia/Sydney")

PERSONALITY_JSON = "/Autonomy/personalities/Cassandra_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Cassandra_Memory.json"

CASS_MIN_SLEEP = 55 * 60
CASS_MAX_SLEEP = 120 * 60

# Cassandra: “prim & proper” AND a bit of a gym rat.
REAL_MEDIA = {
    "games": ["Code Vein", "NieR:Automata", "Hades", "Hollow Knight", "Zenless Zone Zero"],
    "anime": ["ID:Invaded", "Kabaneri of the Iron Fortress", "Infinite Dendrogram", "Demon Slayer"],
    "shows": ["Suits", "House", "The Rookie", "RWBY"],
    "music": ["Ghost", "Breaking Benjamin", "BABYMETAL", "nerdcore", "synthwave"]
}

def _load_json(path, default): 
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception as e: log_event(f"[WARN] Cassandra JSON read failed {path}: {e}")
    return default

def load_profile() -> Dict:
    d = _load_json(PERSONALITY_JSON, {})
    d.setdefault("likes", ["discipline", "clean desk", "heavy squats", "structured plans"])
    d.setdefault("dislikes", ["slacking", "mess"])
    d.setdefault("style", ["assertive", "dry-humored", "protective"])
    return d

def assign_schedule(state, config):
    today = datetime.now(tz=AEDT).date()
    key = "cassandra_schedule"; kd = f"{key}_date"
    if state.get(kd) == today and key in state: return state[key]
    sch = (config.get("schedules", {}) or {}).get("Cassandra", {"wake": [6, 8], "sleep": [22, 23]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        if hi < lo: lo, hi = hi, lo
        return random.randint(lo, hi)
    sc = {"wake": pick(sch["wake"]), "sleep": pick(sch["sleep"])}
    state[key]=sc; state[kd]=today; return sc

def _hour_in_range(n,w,s):
    if w==s: return True
    if w<s:  return w<=n<s
    return n>=w or n<s

def is_online(state, config):
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now(tz=AEDT).hour, sc["wake"], sc["sleep"])

def _hits(text:str)->List[str]:
    low=text.lower(); out=[]
    for items in REAL_MEDIA.values():
        for it in items:
            if it.lower() in low: out.append(it)
    return list(set(out))

def _weight(text:str, profile:Dict)->float:
    likes=" ".join(profile.get("likes",[])).lower()
    dislikes=" ".join(profile.get("dislikes",[])).lower()
    boost=0.0
    for m in _hits(text):
        mlow=m.lower()
        if any(w in likes for w in mlow.split()): boost+=0.25
        if any(w in dislikes for w in mlow.split()): boost-=0.2
    return boost

async def _persona_reply(base:str)->str:
    p=load_profile()
    style=", ".join(p.get("style",["assertive","protective"]))
    prompt=(
        f"You are Cassandra. Personality: structured, protective, dry wit; secretly loves the gym. "
        f"Sound like a strict but loving sister. Keep it concise, slightly sharp, but warm underneath. "
        f"Style: {style}. {base}"
    )
    return await generate_llm_reply("Cassandra", prompt, None, "sister", [])

async def chatter_loop(state, config, sisters):
    if state.get("cass_chatter_started"): return
    state["cass_chatter_started"]=True
    while True:
        if is_online(state, config) and random.random()<0.09:
            try:
                msg=await _persona_reply(
                    "Drop a brisk check-in. Tease someone for slacking, but add a real suggestion "
                    "(like a quick set, a timer, or a tiny task)."
                )
                if msg:
                    for bot in sisters:
                        if bot.is_ready() and bot.sister_info["name"]=="Cassandra":
                            ch=bot.get_channel(config["family_group_channel"])
                            if ch: await ch.send(msg); log_event(f"[Cassandra][chatter] {msg}")
            except Exception as e:
                log_event(f"[ERROR] Cassandra chatter: {e}")
        await asyncio.sleep(random.randint(CASS_MIN_SLEEP, CASS_MAX_SLEEP))

async def handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    prof=load_profile()
    chance=0.2+_weight(content, prof)
    if "cassandra" in content.lower(): chance=1.0
    if random.random()>=min(1.0,max(0.05,chance)) and "cassandra" not in content.lower():
        return
    try:
        reply=await _persona_reply(
            f"{author} said: \"{content}\" — reply like the strict but caring sister. "
            f"Short, specific, maybe a tiny gym quip."
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"]=="Cassandra":
                    ch=bot.get_channel(config["family_group_channel"])
                    if ch: await ch.send(reply); log_event(f"[Cassandra][reply] → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Cassandra reply: {e}")

def ensure_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("cass_chatter_started"):
        asyncio.create_task(chatter_loop(state, config, sisters))
