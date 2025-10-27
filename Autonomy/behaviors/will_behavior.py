import os, json, random, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List

from llm import generate_llm_reply
from logger import log_event

AEDT = ZoneInfo("Australia/Sydney")

PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Will_Memory.json"

WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

INTEREST_BOOST = 0.35
IVY_BOOST      = 0.25
RANT_CHANCE    = 0.10

# Will’s fallback favs (per your request)
FALLBACK_FAVS = [
    "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
    "Hollow Knight", "Stardew Valley", "Elden Ring",
    "NieR:Automata", "Zenless Zone Zero", "Little Nightmares",
    "retro game consoles", "PC building", "tech teardown channels",
]

REAL_MEDIA = {
    "games": ["NieR:Automata", "Zenless Zone Zero", "Little Nightmares", "Hades", "Hollow Knight", "Code Vein"],
    "anime": ["ID:Invaded", "Kabaneri of the Iron Fortress", "Infinite Dendrogram", "Demon Slayer"],
    "shows": ["RWBY", "House", "The Rookie", "Suits"],
    "music": ["synthwave", "indie pop playlists", "nerdcore", "Jonathan Young", "Ninja Sex Party", "BABYMETAL"]
}

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e: log_event(f"[WARN] Will JSON read failed {path}: {e}")
    return default

def load_profile()->Dict:
    j=_load_json(PERSONALITY_JSON,{})
    return {
        "interests": j.get("interests", ["tech","games","anime","music"]),
        "dislikes":  j.get("dislikes",  ["drama"]),
        "style":     j.get("style",     ["casual","timid","sometimes playful"]),
        "triggers":  j.get("triggers",  ["hype","memes","nostalgia"]),
        "favorites": j.get("favorites", FALLBACK_FAVS),
    }

def load_memory()->Dict:
    d=_load_json(MEMORY_JSON, {"projects": {}, "recent_notes": []})
    d.setdefault("projects", {}); d.setdefault("recent_notes", [])
    return d

def save_memory(d:Dict):
    try:
        os.makedirs(os.path.dirname(MEMORY_JSON), exist_ok=True)
        with open(MEMORY_JSON,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)
    except Exception as e: log_event(f"[WARN] Will memory write failed: {e}")

def assign_schedule(state, config):
    today=datetime.now(tz=AEDT).date()
    key="will_schedule"; kd=f"{key}_date"
    if state.get(kd)==today and key in state: return state[key]
    sch=(config.get("schedules",{}) or {}).get("Will",{"wake":[10,12],"sleep":[0,2]})
    def pick(span):
        lo,hi=int(span[0]),int(span[1])
        if hi<lo: lo,hi=hi,lo
        return random.randint(lo,hi)
    sc={"wake":pick(sch["wake"]),"sleep":pick(sch["sleep"])}
    state[key]=sc; state[kd]=today; return sc

def _hour_in_range(n,w,s):
    if w==s: return True
    if w<s: return w<=n<s
    return n>=w or n<s

def is_online(state, config):
    sc=assign_schedule(state, config)
    return _hour_in_range(datetime.now(tz=AEDT).hour, sc["wake"], sc["sleep"])

def _hits(text:str)->List[str]:
    low=text.lower(); out=[]
    for items in REAL_MEDIA.values():
        for it in items:
            if it.lower() in low: out.append(it)
    return list(set(out))

def _weight(text:str, profile:Dict)->float:
    likes=" ".join(profile.get("interests",[])).lower()
    boost=0.0
    for m in _hits(text):
        if any(w in likes for w in m.lower().split()): boost+=0.25
    return boost

def _progress_phrase(p: float) -> str:
    if p >= 1.0: return "I actually finished it — quietly proud, kinda."
    if p >= 0.7: return "Almost done; the last bit is the hardest for me."
    if p >= 0.4: return "Somewhere in the middle; I keep second-guessing things."
    return "I just started; it’s barely a thing yet."

async def _persona_reply(base: str, timid=True, rant=False, progress: float=None) -> str:
    profile = load_profile()
    style = ", ".join(profile.get("style", ["casual","timid"]))
    tone  = "hesitant, soft-spoken" if timid else "bolder but still gentle"
    proj  = f" ({_progress_phrase(progress)})" if progress is not None else ""
    extra = "Animated mini-rant, but keep the shy undertone. " if rant else ""
    prompt = (
        f"You are Will. Personality: shy, nerdy, quick to retreat if flustered, but sweet. "
        f"Speak {tone}; style: {style}. Keep it short, real, and sibling-y. {extra}{base}{proj}"
    )
    return await generate_llm_reply("Will", prompt, None, "sister", [])

async def chatter_loop(state, config, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"]=True
    while True:
        if is_online(state, config):
            base_p=0.1
            if random.random()<base_p:
                timid = random.random()>0.25
                rant  = random.random()<RANT_CHANCE
                mem   = load_memory()
                progress = mem["projects"].get("main", {}).get("progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Make a small, nerd-adjacent comment without jargon; maybe ask a sibling a question.",
                        timid=timid, rant=rant, progress=progress
                    )
                    if msg:
                        for bot in sisters:
                            if bot.is_ready() and bot.sister_info["name"]=="Will":
                                ch=bot.get_channel(config["family_group_channel"])
                                if ch: await ch.send(msg); log_event(f"[Will][chatter] {msg}")
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

async def handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    profile=load_profile()
    chance=0.12+_weight(content, profile)
    if author=="Ivy": chance+=IVY_BOOST
    if "will" in content.lower(): chance=1.0
    if random.random()>=min(1.0, max(0.05, chance)) and "will" not in content.lower():
        return
    timid = random.random()>0.25
    rant  = random.random()<RANT_CHANCE
    mem   = load_memory()
    progress = mem["projects"].get("main", {}).get("progress", random.random())
    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — reply shy but sweet; direct and brief.",
            timid=timid, rant=rant, progress=progress
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"]=="Will":
                    ch=bot.get_channel(config["family_group_channel"])
                    if ch: await ch.send(reply); log_event(f"[Will][reply] → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Will reply: {e}")

def ensure_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(chatter_loop(state, config, sisters))
