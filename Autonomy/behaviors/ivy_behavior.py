import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

PERSONALITY_JSON = "/Autonomy/personalities/Ivy_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Ivy_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

MIN_SLEEP = 35 * 60
MAX_SLEEP = 95 * 60
MEDIA_MENTION_BASE = 0.25  # Ivy is pop-savvy, but we still keep it light

def _load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e: log_event(f"[WARN] Ivy JSON read failed {p}: {e}")
    return d

def _save_json(p,d):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)
    except Exception as e: log_event(f"[WARN] Ivy JSON write failed {p}: {e}")

def load_profile()->Dict:
    d=_load_json(PERSONALITY_JSON,{})
    d.setdefault("style", ["playful","snarky","affectionate"])
    d.setdefault("likes", [])
    d.setdefault("media", {})
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
    key,kd="ivy_schedule","ivy_schedule_date"
    if state.get(kd)==today and key in state: return state[key]
    c=(config.get("schedules",{}) or {}).get("Ivy",{"wake":[8,10],"sleep":[23,24]})
    s={"wake":_pick_hour(c.get("wake",[8,10])),"sleep":_pick_hour(c.get("sleep",[23,24]))}
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

def _post(msg, sisters, config, who="Ivy"):
    for bot in sisters:
        if bot.sister_info["name"]==who and bot.is_ready():
            ch=bot.get_channel(config["family_group_channel"])
            if ch: return asyncio.create_task(ch.send(msg))

async def _persona_reply(base: str, spicy: bool, project_progress: Optional[float]):
    spice = "playful, bratty, affectionate snark (but kind)" if spicy else "bubbly, enthusiastic, lightly teasing"
    proj=""
    if project_progress is not None:
        if project_progress<0.4: proj=" Your project is still chaotic; improvising is half the fun."
        elif project_progress<0.8: proj=" Mid-way; messy but moving; you’re remixing ideas."
        else: proj=" Last stretch; bold finishing touches."
    prompt=(f"You are Ivy. Speak with {spice}. Keep it quick and vivid; avoid lectures.{proj} {base}")
    return await generate_llm_reply(sister="Ivy", user_message=prompt, theme=None, role="sister", history=[])

async def ivy_chatter_loop(state, config, sisters):
    if state.get("ivy_chatter_started"): return
    state["ivy_chatter_started"]=True
    while True:
        if is_online(state, config) and random.random()<0.12:
            try:
                msg=await _persona_reply(
                    "Say one lively, mischievous check-in or outfit/DIY note.",
                    spicy=(random.random()<0.7),
                    project_progress=state.get("Ivy_project_progress", random.random()),
                )
                if msg: _post(msg, sisters, config, "Ivy"); log_event(f"[CHATTER] Ivy: {msg}")
            except Exception as e: log_event(f"[ERROR] Ivy chatter: {e}")
        await asyncio.sleep(random.randint(MIN_SLEEP, MAX_SLEEP))

async def ivy_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    profile=load_profile()
    base=0.25  # Ivy is chatty
    if any(k.lower() in content.lower() for k in profile.get("likes", [])): base+=0.10
    pool=_pool(profile); hits=_hits(content,pool)
    if hits: base+=0.10
    if "ivy" in content.lower(): base=1.0
    if random.random()>=min(0.95, base): return

    await asyncio.sleep(random.randint(3,12))

    mhint=""
    if hits and random.random()<MEDIA_MENTION_BASE:
        mhint=f" If it fits, drop {random.choice(hits)} as a cheeky aside."

    msg=await _persona_reply(
        f'{author} said: "{content}". Reply with playful warmth and a dash of snark.{mhint}',
        spicy=(random.random()<0.65),
        project_progress=state.get("Ivy_project_progress", random.random()),
    )
    if msg: _post(msg, sisters, config, "Ivy"); log_event(f"[REPLY] Ivy → {author}: {msg}")

def ensure_ivy_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(ivy_chatter_loop(state, config, sisters))
