import random, asyncio, os, json
from datetime import datetime
from typing import Dict, Optional

from llm import generate_llm_reply
from logger import log_event
from shared_context import (
    recall_or_enrich_prompt,
    remember_after_exchange,
    get_media_reference,
    craft_media_reaction,
)

CASS_PERSONALITY_JSON = "/Autonomy/personalities/Cassandra_Personality.json"

CASS_MIN_SLEEP = 40 * 60
CASS_MAX_SLEEP = 90 * 60

NICKNAMES = {
    "Aria": ["Aria","Ari"], "Selene": ["Selene","Luna"],
    "Cassandra": ["Cassandra","Cass","Cassie"], "Ivy": ["Ivy","Vy"], "Will": ["Will","Willow"]
}
def _pick_name(t): 
    ns=NICKNAMES.get(t,[t]); 
    return random.choice(ns) if random.random()<0.35 else t

def _load_json(path: str, default: dict)->dict:
    try:
        if os.path.exists(path):
            with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Cass JSON read failed {path}: {e}")
    return default

def load_cass_profile()->Dict:
    p=_load_json(CASS_PERSONALITY_JSON,{})
    p.setdefault("style",["disciplined","confident","concise"])
    p.setdefault("core_personality","Disciplined and composed; blunt but fair; action first.")
    return p

def assign_cass_schedule(state: Dict, config: Dict):
    today=datetime.now().date()
    key="cass_schedule"; kd=f"{key}_date"
    if state.get(kd)==today and key in state: return state[key]
    scfg=(config.get("schedules",{}) or {}).get("Cassandra", {"wake":[5,7],"sleep":[21,23]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        if hi < lo: lo, hi = hi, lo
        return random.randint(lo, hi)
    schedule={"wake":pick(scfg["wake"]), "sleep":pick(scfg["sleep"])}
    state[key]=schedule; state[kd]=today; return schedule

def _hr_in(h,w,s):
    if w==s:return True
    if w<s: return w<=h<s
    return h>=w or h<s

def is_cass_online(state,config)->bool:
    sc=assign_cass_schedule(state,config)
    return _hr_in(datetime.now().hour, sc["wake"], sc["sleep"])

async def _persona_reply(base_prompt: str, address_to: Optional[str]=None)->str:
    p=load_cass_profile()
    style=", ".join(p.get("style",["disciplined","concise"]))
    personality=p.get("core_personality","Disciplined and composed; blunt but fair.")
    who=_pick_name(address_to) if address_to else None
    prefix=f"Speak directly to {who} by name. " if who else ""
    prompt=(
        f"You are Cassandra. Personality: {personality}. Speak in a {style} style — assertive, clean, no fluff, but not cruel. "
        f"{prefix}Only first-person. Keep it short and actionable. {base_prompt}"
    )
    return await generate_llm_reply("Cassandra", prompt, None, "sister", [])

async def cass_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("cass_chatter_started"): return
    state["cass_chatter_started"]=True
    while True:
        if is_cass_online(state, config):
            if random.random()<0.12:
                base, mem = recall_or_enrich_prompt(
                    "Cassandra", "Offer a brisk check-in or a quick nudge to keep momentum.", ["workout","order","plan"]
                )
                msg=await _persona_reply(base)
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"]=="Cassandra" and bot.is_ready():
                            ch=bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[CHATTER] Cassandra: {msg}")
                                if mem:
                                    remember_after_exchange("Cassandra", f"Chatted: {mem['summary']}", tone="firm", tags=["chatter"])
                                break
        await asyncio.sleep(random.randint(CASS_MIN_SLEEP, CASS_MAX_SLEEP))

def _cool_ok(state: Dict, channel_id: int)->bool:
    cd=state.setdefault("cooldowns",{}).setdefault("Cassandra",{})
    last=cd.get(channel_id,0); now=datetime.now().timestamp()
    if now-last<120: return False
    cd[channel_id]=now; return True

async def cass_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int)->bool:
    if not is_cass_online(state,config): return False
    if not _cool_ok(state,channel_id):   return False

    rot=state.get("rotation",{"lead":None,"supports":[],"rest":None})
    chance=0.20
    if rot.get("lead")=="Cassandra": chance=0.70
    elif "Cassandra" in rot.get("supports",[]): chance=0.45
    elif rot.get("rest")=="Cassandra": chance=0.25
    if "cassandra" in content.lower() or "cass" in content.lower(): chance=1.0

    inject=None
    if any(k in content.lower() for k in ["doc","plan","show","film","music","anime","gym","lift","workout"]):
        m=get_media_reference("Cassandra", mood_tags=["discipline","strategy","documentary","drama"])
        if m: inject=craft_media_reaction("Cassandra", m)

    if random.random()>chance: return False

    addressed=author
    base=f'Respond to {addressed} with one clear point about "{content}". Keep it crisp and constructive.'
    if inject: base+=f" If it fits, add: {inject}"

    msg=await _persona_reply(base,address_to=addressed)
    if not msg: return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"]=="Cassandra":
            ch=bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(msg)
                log_event(f"[REPLY] Cassandra → {addressed}: {msg}")
                remember_after_exchange("Cassandra", f"Replied to {addressed}", tone="firm", tags=["reply"])
                return True
    return False

def ensure_cass_systems(state: Dict, config: Dict, sisters):
    assign_cass_schedule(state, config)
    if not state.get("cass_chatter_started"):
        asyncio.create_task(cass_chatter_loop(state, config, sisters))
