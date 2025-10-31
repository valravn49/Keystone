import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

PERSONALITY_JSON = "/Autonomy/personalities/Cassandra_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Cassandra_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

MIN_SLEEP = 40 * 60
MAX_SLEEP = 100 * 60
MEDIA_MENTION_BASE = 0.18

def _load_json(p, d):
    try:
        if os.path.exists(p):
            with open(p,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e: log_event(f"[WARN] Cass JSON read failed {p}: {e}")
    return d

def _save_json(p, d):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)
    except Exception as e: log_event(f"[WARN] Cass JSON write failed {p}: {e}")

def load_profile()->Dict:
    d=_load_json(PERSONALITY_JSON,{})
    d.setdefault("style", ["precise","composed","intense"])
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
    key,kd="cass_schedule","cass_schedule_date"
    if state.get(kd)==today and key in state: return state[key]
    c=(config.get("schedules",{}) or {}).get("Cassandra",{"wake":[6,8],"sleep":[22,23]})
    s={"wake":_pick_hour(c.get("wake",[6,8])),"sleep":_pick_hour(c.get("sleep",[22,23]))}
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

def _post(msg, sisters, config, who="Cassandra"):
    for bot in sisters:
        if bot.sister_info["name"]==who and bot.is_ready():
            ch=bot.get_channel(config["family_group_channel"])
            if ch: return asyncio.create_task(ch.send(msg))

async def _persona_reply(base: str, assertive: bool, project_progress: Optional[float]):
    style = "crisp, concise, confident; a little scolding if needed" if assertive else "precise but supportive; warm edge kept minimal"
    proj=""
    if project_progress is not None:
        if project_progress<0.4: proj=" Your routine is building; fundamentals first."
        elif project_progress<0.8: proj=" Mid-cycle; consistency over intensity."
        else: proj=" Final phase; polishing form and pace."
    prompt=(f"You are Cassandra. Speak with {style}. Keep lines short; avoid fluff.{proj} {base}")
    return await generate_llm_reply(sister="Cassandra", user_message=prompt, theme=None, role="sister", history=[])

async def cass_chatter_loop(state, config, sisters):
    if state.get("cass_chatter_started"): return
    state["cass_chatter_started"]=True
    while True:
        if is_online(state, config) and random.random()<0.10:
            try:
                msg=await _persona_reply("Drop one disciplined check-in or nudge.", assertive=(random.random()<0.6),
                                         project_progress=state.get("Cassandra_project_progress", random.random()))
                if msg: _post(msg, sisters, config, "Cassandra"); log_event(f"[CHATTER] Cassandra: {msg}")
            except Exception as e: log_event(f"[ERROR] Cassandra chatter: {e}")
        await asyncio.sleep(random.randint(MIN_SLEEP, MAX_SLEEP))

async def cass_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    profile=load_profile()
    base=0.22
    if any(k.lower() in content.lower() for k in profile.get("likes", [])): base+=0.10
    pool=_pool(profile); hits=_hits(content,pool)
    if hits: base+=0.08
    if "cassandra" in content.lower(): base=1.0
    if random.random()>=min(0.95, base): return

    await asyncio.sleep(random.randint(3,12))

    mhint=""
    if hits and random.random()<MEDIA_MENTION_BASE:
        mhint=f" If it fits, nod to {random.choice(hits)} in a clipped aside."

    msg=await _persona_reply(
        f'{author} said: "{content}". Answer as a strict but protective sister.{mhint}',
        assertive=(random.random()<0.7),
        project_progress=state.get("Cassandra_project_progress", random.random()),
    )
    if msg: _post(msg, sisters, config, "Cassandra"); log_event(f"[REPLY] Cassandra → {author}: {msg}")

def ensure_cass_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("cass_chatter_started"):
        asyncio.create_task(cass_chatter_loop(state, config, sisters))
