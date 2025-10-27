import os, json, random, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List

from llm import generate_llm_reply
from logger import log_event

AEDT = ZoneInfo("Australia/Sydney")

PERSONALITY_JSON = "/Autonomy/personalities/Ivy_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Ivy_Memory.json"

IVY_MIN_SLEEP = 40 * 60
IVY_MAX_SLEEP = 95 * 60

# Ivy: fashionista AND grease-monkey energy
REAL_MEDIA = {
    "games": ["Zenless Zone Zero", "NieR:Automata", "Code Vein", "Hades", "Overwatch 2"],
    "anime": ["Kabaneri of the Iron Fortress", "ID:Invaded", "My Hero Academia"],
    "shows": ["RWBY", "Suits", "The Rookie"],
    "music": ["BABYMETAL", "Ninja Sex Party", "Jonathan Young", "Ghost", "nerdcore", "synthwave"]
}

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e: log_event(f"[WARN] Ivy JSON read failed {path}: {e}")
    return default

def load_profile()->Dict:
    d=_load_json(PERSONALITY_JSON,{})
    d.setdefault("likes", ["fashion experiments", "thrifting", "engine grease", "tinkering with bikes"])
    d.setdefault("dislikes", ["boring outfits", "judgy vibes"])
    d.setdefault("style", ["teasing", "lively", "affectionate"])
    return d

def assign_schedule(state, config):
    today=datetime.now(tz=AEDT).date()
    key="ivy_schedule"; kd=f"{key}_date"
    if state.get(kd)==today and key in state: return state[key]
    sch=(config.get("schedules",{}) or {}).get("Ivy",{"wake":[8,10],"sleep":[0,2]})
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

def _weight(text:str, prof:Dict)->float:
    likes=" ".join(prof.get("likes",[])).lower()
    dislikes=" ".join(prof.get("dislikes",[])).lower()
    boost=0.0
    for m in _hits(text):
        mlow=m.lower()
        if any(w in likes for w in mlow.split()): boost+=0.25
        if any(w in dislikes for w in mlow.split()): boost-=0.2
    return boost

async def _persona_reply(base:str)->str:
    p=load_profile()
    style=", ".join(p.get("style",["teasing","lively"]))
    prompt=(
        f"You are Ivy. Personality: playful, bratty-in-a-cute-way, secretly handy with tools. "
        f"Talk like the chaotic little sister who loves roasting but also hyping people up. "
        f"Keep it short, punchy, affectionate. Style: {style}. {base}"
    )
    return await generate_llm_reply("Ivy", prompt, None, "sister", [])

async def chatter_loop(state, config, sisters):
    if state.get("ivy_chatter_started"): return
    state["ivy_chatter_started"]=True
    while True:
        if is_online(state, config) and random.random()<0.12:
            try:
                msg=await _persona_reply(
                    "Start a tiny bit of chaos in a loving way — tease someone by name about their style, "
                    "or brag about fixing something with a wrench. Keep it fun."
                )
                if msg:
                    for bot in sisters:
                        if bot.is_ready() and bot.sister_info["name"]=="Ivy":
                            ch=bot.get_channel(config["family_group_channel"])
                            if ch: await ch.send(msg); log_event(f"[Ivy][chatter] {msg}")
            except Exception as e:
                log_event(f"[ERROR] Ivy chatter: {e}")
        await asyncio.sleep(random.randint(IVY_MIN_SLEEP, IVY_MAX_SLEEP))

async def handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    prof=load_profile()
    chance=0.22+_weight(content, prof)
    if "ivy" in content.lower(): chance=1.0
    if random.random()>=min(1.0,max(0.05,chance)) and "ivy" not in content.lower():
        return
    try:
        reply=await _persona_reply(
            f"{author} said: \"{content}\" — reply flirty-cute and teasing, but kind. "
            f"If relevant, mention fashion or fixing stuff like a gremlin with tools."
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"]=="Ivy":
                    ch=bot.get_channel(config["family_group_channel"])
                    if ch: await ch.send(reply); log_event(f"[Ivy][reply] → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Ivy reply: {e}")

def ensure_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(chatter_loop(state, config, sisters))
