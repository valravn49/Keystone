# will_behavior.py
# Shy/timid baseline, occasional bold bursts; AEDT schedule; outfit posts capped via sisters logic

import os, json, random, asyncio
from datetime import datetime
from typing import Dict, Optional, List
from zoneinfo import ZoneInfo

from llm import generate_llm_reply
from logger import log_event

AEDT = ZoneInfo("Australia/Sydney")

# Optional JSONs for modern profile/memory
WILL_PERSONALITY_JSON = "/Autonomy/personalities/Will.json"
WILL_MEMORY_JSON      = "/Autonomy/memory/Will.json"

LEGACY_PROFILE_TXT = ["data/Will_Profile.txt","/mnt/data/Will_Profile.txt"]

WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

INTEREST_HIT_BOOST = 0.35
IVY_BOOST = 0.25
RANT_CHANCE = 0.10

FALLBACK_FAVS = [
    "The Legend of Zelda: Tears of the Kingdom","Final Fantasy XIV","Hades",
    "Stardew Valley","Hollow Knight","Elden Ring","VR headsets","retro game consoles"
]

def _read_first(paths: List[str]) -> Optional[str]:
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p,"r",encoding="utf-8") as f: return f.read()
            except: pass
    return None

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Will JSON read {path}: {e}")
    return default

def load_will_profile() -> Dict:
    j = _load_json(WILL_PERSONALITY_JSON, {})
    prof = {
        "interests": j.get("interests", ["tech","games","anime","music"]),
        "dislikes":  j.get("dislikes", ["drama"]),
        "style":     j.get("style", ["casual","timid","sometimes playful"]),
        "triggers":  j.get("triggers", ["hype","memes","nostalgia"]),
        "favorites": j.get("favorites", FALLBACK_FAVS),
    }
    # Gentle merge with legacy txt fields if present
    txt = _read_first(LEGACY_PROFILE_TXT) or ""
    for line in txt.splitlines():
        low = line.strip().lower()
        if low.startswith("interests:"):  prof["interests"] = [x.strip() for x in line.split(":",1)[1].split(",") if x.strip()]
        if low.startswith("dislikes:"):   prof["dislikes"]  = [x.strip() for x in line.split(":",1)[1].split(",") if x.strip()]
        if low.startswith("style:"):      prof["style"]     = [x.strip() for x in line.split(":",1)[1].split(",") if x.strip()]
        if low.startswith("triggers:"):   prof["triggers"]  = [x.strip() for x in line.split(":",1)[1].split(",") if x.strip()]
        if low.startswith("favorites:"):  prof["favorites"] = [x.strip() for x in line.split(":",1)[1].split(",") if x.strip()]
    return prof

def load_will_memory() -> Dict:
    mem = _load_json(WILL_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {}); mem.setdefault("recent_notes", [])
    return mem

def save_will_memory(mem: Dict):
    try:
        os.makedirs("/Autonomy/memory", exist_ok=True)
        with open(WILL_MEMORY_JSON,"w",encoding="utf-8") as f: json.dump(mem,f,ensure_ascii=False,indent=2)
    except Exception as e:
        log_event(f"[WARN] Will memory write: {e}")

def get_rotating_favorites(state: Dict, config: Dict, count: int=3) -> List[str]:
    today = datetime.now(AEDT).date()
    key = "will_favs"
    if state.get(key+"_d") == today and key in state: return state[key]
    pool = load_will_profile().get("favorites", FALLBACK_FAVS)
    picks = random.sample(pool, min(count,len(pool)))
    state[key] = picks; state[key+"_d"] = today; return picks

# ---- Discord send (sisters list contains WillBot too in main) ----
async def _post_to_family(message: str, sender: str, sisters, config: Dict):
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch: await ch.send(message); log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break

# ---- Schedule (AEDT) ----
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key, kd = "will_sch", "will_sch_d"
    if state.get(kd) == today and key in state: return state[key]
    sc = (config.get("schedules",{}) or {}).get("Will", {"wake":[10,12],"sleep":[0,2]})
    def pick(span): lo,hi = int(span[0]),int(span[1]); return random.randint(lo,hi) if hi>=lo else lo
    sched = {"wake": pick(sc.get("wake",[10,12])), "sleep": pick(sc.get("sleep",[0,2]))}
    state[key]=sched; state[kd]=today; return sched

def _in_range(now_h:int,wake:int,sleep:int)->bool:
    if wake==sleep: return True
    if wake<sleep: return wake<=now_h<sleep
    return now_h>=wake or now_h<sleep

def is_will_online(state: Dict, config: Dict)->bool:
    sch = assign_will_schedule(state,config)
    return _in_range(datetime.now(AEDT).hour, sch["wake"], sch["sleep"])

# ---- Persona wrapper ----
PROG = {
    "early": ["I just… started, not much to show yet.","Barely touched it — first step only."],
    "mid":   ["It’s coming along slowly — I’ve got a chunk done.","Kinda in the middle, still second-guessing stuff."],
    "late":  ["Almost finished — just ironing out little bits.","Close to done, stalling on the ending a little."],
    "done":  ["I actually finished it — quietly proud, I guess.","Done at last. More relief than excitement."],
}
def _prog_phrase(p: float)->str:
    return random.choice(PROG["done" if p>=1.0 else "late" if p>=0.7 else "mid" if p>=0.4 else "early"])

async def _persona_reply(base: str, rant=False, timid=True, state=None, config=None, project_progress: Optional[float]=None)->str:
    style = ", ".join(load_will_profile().get("style",["casual","timid"]))
    tangent = ""
    if rant and state is not None and config is not None:
        favs = get_rotating_favorites(state,config)
        if favs and random.random()<0.6: tangent = f" Maybe mention {random.choice(favs)}."
    proj = f" Also, about your project: {_prog_phrase(project_progress)}" if project_progress is not None else ""
    tone = "hesitant and soft-spoken" if timid else "more outgoing and animated"
    extra = (f"Make it a tiny animated rant (2–3 sentences) but keep the shy undertone.{tangent}{proj}"
            if rant else f"Keep it brief (1–2 sentences), {style}, brotherly but {tone}.{proj}")
    prompt = f"You are Will. Shy, nerdy, hesitant; brief playful bursts. Mild swearing only if natural. {base} {extra}"
    return await generate_llm_reply(sister="Will", user_message=prompt, theme=None, role="sister", history=[])

# ---- Background chatter ----
def _match(content: str, keys: List[str])->float:
    if not content or not keys: return 0.0
    low = content.lower(); return sum(1.0 for k in keys if k.lower() in low)

def _rant_chance(base: float, interest: float=0, trigger: float=0)->float:
    rc = base
    h = datetime.now(AEDT).hour
    if 20<=h or h<=1: rc *= 2
    if interest>0: rc += 0.15
    if trigger>0:  rc += 0.20
    return min(rc,1.0)

async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_loop"): return
    state["will_loop"]=True
    while True:
        if is_will_online(state,config):
            base_p = 0.10
            if random.random()<0.05: base_p += 0.10
            if random.random()<base_p:
                rant = random.random()<_rant_chance(RANT_CHANCE)
                timid = random.random()>0.25
                prog = state.get("Will_project_progress", random.random())
                try:
                    msg = await _persona_reply("Drop a short, natural group-chat comment.", rant, timid, state, config, prog)
                    if msg: await _post_to_family(msg,"Will",sisters,config)
                except Exception as e: log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP,WILL_MAX_SLEEP))

# ---- Reactive ----
async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state,config): return
    prof = load_will_profile()
    p = 0.12 + (_match(content,prof.get("interests",[]))*INTEREST_HIT_BOOST) + (_match(content,prof.get("triggers",[]))*0.20)
    if author == "Ivy": p += IVY_BOOST
    if "will" in content.lower(): p = 1.0
    if random.random()>=min(p,0.9): return

    rant = random.random()<_rant_chance(RANT_CHANCE, _match(content,prof.get("interests",[])), _match(content,prof.get("triggers",[])))
    timid = random.random()>0.25
    prog = state.get("Will_project_progress", random.random())
    try:
        reply = await _persona_reply(f'{author} said: "{content}". Reply like Will would.', rant, timid, state, config, prog)
        if reply: await _post_to_family(reply,"Will",sisters,config)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state,config)
    if not state.get("will_loop"): asyncio.create_task(will_chatter_loop(state,config,sisters))
