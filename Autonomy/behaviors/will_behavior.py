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

WILL_PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"

WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60
RANT_CHANCE = 0.10

NICKNAMES = {
    "Aria": ["Aria","Ari"], "Selene": ["Selene","Luna"],
    "Cassandra": ["Cassandra","Cass","Cassie"], "Ivy": ["Ivy","Vy"],
    "Will": ["Will","Willow"]
}
def _pick_name(t):
    ns=NICKNAMES.get(t,[t]); 
    return random.choice(ns) if random.random()<0.35 else t

def _load_json(path: str, default: dict)->dict:
    try:
        if os.path.exists(path):
            with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Will JSON read failed {path}: {e}")
    return default

def load_will_profile()->Dict:
    p=_load_json(WILL_PERSONALITY_JSON,{})
    p.setdefault("style",["timid","reflective","sometimes playful"])
    p.setdefault("core_personality","Shy, creative, observant; warm once comfortable.")
    return p

def assign_will_schedule(state: Dict, config: Dict):
    today=datetime.now().date()
    key="will_schedule"; kd=f"{key}_date"
    if state.get(kd)==today and key in state: return state[key]
    scfg=(config.get("schedules",{}) or {}).get("Will", {"wake":[10,12],"sleep":[0,2]})
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

def is_will_online(state,config)->bool:
    sc=assign_will_schedule(state,config)
    return _hr_in(datetime.now().hour, sc["wake"], sc["sleep"])

async def _persona_reply(base_prompt: str, timid: bool=True, address_to: Optional[str]=None, rant: bool=False)->str:
    p=load_will_profile()
    style=", ".join(p.get("style",["timid","reflective"]))
    personality=p.get("core_personality","Shy, creative, observant.")
    who=_pick_name(address_to) if address_to else None
    prefix=f"Speak directly to {who} by name. " if who else ""
    tone = "hesitant and soft-spoken" if timid else "more animated but still gentle"
    extra = "Make it a small enthusiastic tangent (2–3 sentences) but keep the shy undertone." if rant else "Keep it brief (1–2 sentences)."
    prompt=(
        f"You are Will. Personality: {personality}. Speak in a {style} style, {tone}. "
        f"{prefix}Only first-person. {extra} {base_prompt}"
    )
    return await generate_llm_reply("Will", prompt, None, "sister", [])

async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"]=True
    while True:
        if is_will_online(state, config):
            if random.random()<0.10:
                base, mem = recall_or_enrich_prompt(
                    "Will", "Share one gentle note or tiny creative thought.", ["art","game","coffee","light"]
                )
                rant = random.random()<RANT_CHANCE
                msg=await _persona_reply(base, timid=(not rant), rant=rant)
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"]=="Will" and bot.is_ready():
                            ch=bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[CHATTER] Will: {msg}")
                                if mem:
                                    remember_after_exchange("Will", f"Chatted: {mem['summary']}", tone="warm", tags=["chatter"])
                                break
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

def _cool_ok(state: Dict, channel_id: int)->bool:
    cd=state.setdefault("cooldowns",{}).setdefault("Will",{})
    last=cd.get(channel_id,0); now=datetime.now().timestamp()
    if now-last<120: return False
    cd[channel_id]=now; return True

async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int)->bool:
    if not is_will_online(state,config): return False
    if not _cool_ok(state,channel_id):  return False

    rot=state.get("rotation",{"lead":None,"supports":[],"rest":None})
    chance=0.20
    if rot.get("lead")=="Will": chance=0.70
    elif "Will" in rot.get("supports",[]): chance=0.45
    elif rot.get("rest")=="Will": chance=0.25
    if "will" in content.lower(): chance=1.0

    inject=None
    if any(k in content.lower() for k in ["anime","game","show","music","cosplay","art","photo","coffee"]):
        m=get_media_reference("Will", mood_tags=["anime","jrpg","indie","nintendo"])
        if m: inject=craft_media_reaction("Will", m)

    if random.random()>chance: return False

    addressed=author
    rant = random.random()<RANT_CHANCE
    base=f'Respond to {addressed} about "{content}". Be sincere and specific.'
    if inject: base+=f" If it fits, add: {inject}"

    msg=await _persona_reply(base, timid=(not rant), rant=rant, address_to=addressed)
    if not msg: return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"]=="Will":
            ch=bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(msg)
                log_event(f"[REPLY] Will → {addressed}: {msg}")
                remember_after_exchange("Will", f"Replied to {addressed}", tone="warm", tags=["reply"])
                return True
    return False

def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
