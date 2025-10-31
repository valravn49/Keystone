import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from llm import generate_llm_reply
from logger import log_event

PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Selene_Memory.json"
AEDT = pytz.timezone("Australia/Sydney")

MIN_SLEEP = 45 * 60
MAX_SLEEP = 110 * 60
MEDIA_MENTION_BASE = 0.20

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Selene JSON read failed {path}: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
    except Exception as e:
        log_event(f"[WARN] Selene JSON write failed {path}: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSONALITY_JSON, {})
    d.setdefault("style", ["warm","soothing","playfully bold"])
    d.setdefault("likes", [])
    d.setdefault("media", {})
    return d

def load_memory() -> Dict:
    d = _load_json(MEMORY_JSON, {"projects": {}, "recent_notes": []})
    d.setdefault("projects", {}); d.setdefault("recent_notes", [])
    return d

def save_memory(mem: Dict): _save_json(MEMORY_JSON, mem)

def _pick_hour(span: List[int]) -> int:
    lo, hi = int(span[0]), int(span[1])
    if hi < lo: lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key,kd = "selene_schedule","selene_schedule_date"
    if state.get(kd)==today and key in state: return state[key]
    c = (config.get("schedules",{}) or {}).get("Selene",{"wake":[7,9],"sleep":[22,23]})
    schedule = {"wake": _pick_hour(c.get("wake",[7,9])), "sleep": _pick_hour(c.get("sleep",[22,23]))}
    state[key]=schedule; state[kd]=today; return schedule

def _hour_in_range(now_h:int, wake:int, sleep:int)->bool:
    if wake==sleep: return True
    if wake<sleep:  return wake<=now_h<sleep
    return now_h>=wake or now_h<sleep

def is_online(state: Dict, config: Dict)->bool:
    sc = assign_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

def _media_pool(profile: Dict)->List[str]:
    out=[]; m=profile.get("media",{})
    for v in m.values():
        if isinstance(v,list): out.extend(v)
    return out

def _media_hits(text:str, pool:List[str])->List[str]:
    t=text.lower(); hits=[]
    for m in pool:
        if m.lower() in t: hits.append(m)
    return list(set(hits))

def _post(msg:str, sisters, config:Dict, who="Selene"):
    for bot in sisters:
        if bot.sister_info["name"]==who and bot.is_ready():
            ch=bot.get_channel(config["family_group_channel"])
            if ch: return asyncio.create_task(ch.send(msg))

async def _persona_reply(base: str, cozy: bool, sensory: bool, project_progress: Optional[float]):
    profile = load_profile()
    tone = "warm, nurturing, gently playful" if cozy else "steady, direct, still kind"
    sens = " Add a small sensory detail (weather, smell, texture)." if sensory else ""
    proj = ""
    if project_progress is not None:
        if project_progress < 0.4: proj=" Your personal project is just starting; simple prep."
        elif project_progress < 0.8: proj=" Mid-way and satisfying; small steps add up."
        else: proj=" Nearly finished; you’re polishing for comfort."
    prompt = (f"You are Selene. Speak with {tone}. Keep it natural and sibling-like.{sens}{proj} {base}")
    return await generate_llm_reply(sister="Selene", user_message=prompt, theme=None, role="sister", history=[])

async def selene_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("selene_chatter_started"): return
    state["selene_chatter_started"]=True
    while True:
        if is_online(state, config) and random.random()<0.10:
            try:
                msg = await _persona_reply(
                    "Say one gentle, practical check-in or small plan for the day.",
                    cozy=True, sensory=(random.random()<0.6),
                    project_progress=state.get("Selene_project_progress", random.random()),
                )
                if msg: _post(msg, sisters, config, "Selene"); log_event(f"[CHATTER] Selene: {msg}")
            except Exception as e:
                log_event(f"[ERROR] Selene chatter: {e}")
        await asyncio.sleep(random.randint(MIN_SLEEP, MAX_SLEEP))

async def selene_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_online(state, config): return
    profile = load_profile()
    base = 0.22
    if any(k.lower() in content.lower() for k in profile.get("likes", [])): base += 0.10

    pool=_media_pool(profile); hits=_media_hits(content, pool)
    if hits: base+=0.10
    if "selene" in content.lower(): base=1.0
    if random.random()>=min(0.95, base): return

    await asyncio.sleep(random.randint(3,12))

    mhint=""
    if hits and random.random()<MEDIA_MENTION_BASE:
        mhint=f" If natural, nod to {random.choice(hits)} in one short phrase."

    msg = await _persona_reply(
        f'{author} said: "{content}". Reply as a warm, slightly teasing caretaker.{mhint}',
        cozy=True, sensory=(random.random()<0.5),
        project_progress=state.get("Selene_project_progress", random.random()),
    )
    if msg: _post(msg, sisters, config, "Selene"); log_event(f"[REPLY] Selene → {author}: {msg}")

def ensure_selene_systems(state: Dict, config: Dict, sisters):
    assign_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(selene_chatter_loop(state, config, sisters))
