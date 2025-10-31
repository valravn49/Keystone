import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Will_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

MIN_SLEEP = 40 * 60
MAX_SLEEP = 100 * 60
MEDIA_MENTION_BASE = 0.20

# Shy baseline; occasional animated bursts
RANT_CHANCE_BASE = 0.10

def _load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e: log_event(f"[WARN] Will JSON read failed {p}: {e}")
    return d

def _save_json(p,d):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)
    except Exception as e: log_event(f"[WARN] Will JSON write failed {p}: {e}")

def load_profile()->Dict:
    d=_load_json(PERSONALITY_JSON,{})
    d.setdefault("style", ["casual","timid","sometimes playful"])
    d.setdefault("likes", [])
    d.setdefault("media", {})
    # Ensure your fallback favorites are included
    favs = set(d.get("media", {}).get("games", []) + [
        "Nier: Automata","Zenless Zone Zero","Little Nightmares"
    ])
    d["media"].setdefault("games", list(favs))
    return d

def load_memory()->Dict:
    d=_load_json(MEMORY_JSON, {"projects": {}, "recent_notes": []})
    d.setdefault("projects", {}); d.setdefault("recent_notes", [])
    return d

def save_memory(mem: Dict): _save_json(MEMORY_JSON, mem)

def _pick_hour(span):
    lo, hi = int(span[0]), int(span[1])
    if hi < lo: lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key,kd="will_schedule","will_schedule_date"
    if state.get(kd)==today and key in state: return state[key]
    c=(config.get("schedules",{}) or {}).get("Will",{"wake":[10,12],"sleep":[0,2]})
    s={"wake":_pick_hour(c.get("wake",[10,12])),"sleep":_pick_hour(c.get("sleep",[0,2]))}
    state[key]=s; state[kd]=today; return s

def _hour_in_range(h,w,s):
    if w==s: return True
    if w<s:  return w<=h<s
    return h>=w or h<s

def is_online(state, config)->bool:
    sc=assign_schedule(state, config); now_h=datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

def _pool(profile):
    out=[]; m=profile.get("media",{})
    for v in m.values():
        if isinstance(v,list): out.extend(v)
    return out

def _hits(text,pool):
    t=text.lower(); res=[]
    for m in pool:
        if m.lower() in t: res.append(m)
    return list(set(res))

def _post(msg, sisters, config, who="Will"):
    for bot in sisters:
        if bot.sister_info["name"]==who and bot.is_ready():
            ch=bot.get_channel(config["family_group_channel"])
            if ch: return asyncio.create_task(ch.send(msg))

def _rant_chance(now_hour:int, base:float)->float:
    chance=base
    if 20 <= now_hour or now_hour <= 1: chance *= 2
    return min(chance, 0.8)

async def _persona_reply(base: str, timid: bool, animated: bool, project_progress: Optional[float]):
    tone = "hesitant, soft-spoken" if timid else "more outgoing and animated (still gentle)"
    proj=""
    if project_progress is not None:
        if project_progress<0.4: proj=" Your project’s barely started; you’re feeling it out."
        elif project_progress<0.8: proj=" Mid-way; you’re second-guessing details, but it’s moving."
        else: proj=" Almost done; you’re polishing, quietly proud."
    mode = " Make it a small, animated riff (2 sentences max) if it feels right." if animated else " Keep it short (1–2 sentences)."
    prompt=(f"You are Will. Speak with a {tone} tone; avoid heavy slang; keep it human and sincere.{proj}{mode} {base}")
    return await generate_llm_reply(sister="Will", user_message=prompt, theme=None, role="sister", history=[])

async def will_chatter_loop(state, config, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"]=True
    while True:
        if is_online(state, config) and random.random()<0.10:
            try:
                now_h = datetime.now(AEDT).hour
                animated = (random.random() < _rant_chance(now_h, RANT_CHANCE_BASE))
                timid = not animated or (random.random() < 0.7)
                msg=await _persona_reply(
                    "Share one small, creative observation or cozy thought.",
                    timid=timid, animated=animated,
                    project_progress=state.get("Will_project_progress", random.random())
                )
                if msg: _post(msg, sisters, config, "Will"); log_event(f"[CHATTER] Will: {msg}")
            except Exception as e: log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(MIN_SLEEP, MAX_SLEEP))

async def will_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    profile=load_profile()
    base=0.20  # shy, but reachable
    if any(k.lower() in content.lower() for k in profile.get("likes", [])): base+=0.12
    pool=_pool(profile); hits=_hits(content,pool)
    if hits: base+=0.10
    if "will" in content.lower(): base=1.0
    if random.random()>=min(0.95, base): return

    await asyncio.sleep(random.randint(3,12))

    mhint=""
    if hits and random.random()<MEDIA_MENTION_BASE:
        mhint=f" If natural, glance at {random.choice(hits)} in a single phrase."

    now_h = datetime.now(AEDT).hour
    animated = (random.random() < _rant_chance(now_h, RANT_CHANCE_BASE))
    timid = not animated or (random.random() < 0.75)

    msg=await _persona_reply(
        f'{author} said: "{content}". Reply in your shy, thoughtful way.{mhint}',
        timid=timid, animated=animated,
        project_progress=state.get("Will_project_progress", random.random())
    )
    if msg: _post(msg, sisters, config, "Will"); log_event(f"[REPLY] Will → {author}: {msg}")

def ensure_will_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
