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

IVY_PERSONALITY_JSON = "/Autonomy/personalities/Ivy_Personality.json"

IVY_MIN_SLEEP = 35 * 60
IVY_MAX_SLEEP = 85 * 60

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
        log_event(f"[WARN] Ivy JSON read failed {path}: {e}")
    return default

def load_ivy_profile()->Dict:
    p=_load_json(IVY_PERSONALITY_JSON,{})
    p.setdefault("style",["playful","teasing","rebellious"])
    p.setdefault("core_personality","Playful chaos with real skill; quick humor, emotive slang.")
    return p

def assign_ivy_schedule(state: Dict, config: Dict):
    today=datetime.now().date()
    key="ivy_schedule"; kd=f"{key}_date"
    if state.get(kd)==today and key in state: return state[key]
    scfg=(config.get("schedules",{}) or {}).get("Ivy", {"wake":[8,10],"sleep":[23,1]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        # allow wrap by swapping if needed
        if hi < lo: lo, hi = hi, lo
        return random.randint(lo, hi)
    schedule={"wake":pick(scfg["wake"]), "sleep":pick(scfg["sleep"])}
    state[key]=schedule; state[kd]=today; return schedule

def _hr_in(h,w,s):
    if w==s:return True
    if w<s: return w<=h<s
    return h>=w or h<s

def is_ivy_online(state,config)->bool:
    sc=assign_ivy_schedule(state,config)
    return _hr_in(datetime.now().hour, sc["wake"], sc["sleep"])

async def _persona_reply(base_prompt: str, address_to: Optional[str]=None)->str:
    p=load_ivy_profile()
    style=", ".join(p.get("style",["playful","teasing"]))
    personality=p.get("core_personality","Playful chaos with skill; quick humor.")
    who=_pick_name(address_to) if address_to else None
    prefix=f"Speak directly to {who} by name. " if who else ""
    prompt=(
        f"You are Ivy. Personality: {personality}. Speak in a {style} style — witty, cheeky, but affectionate. "
        f"{prefix}Only first-person. Keep it punchy, a little snarky even when respectful. {base_prompt}"
    )
    return await generate_llm_reply("Ivy", prompt, None, "sister", [])

async def ivy_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("ivy_chatter_started"): return
    state["ivy_chatter_started"]=True
    while True:
        if is_ivy_online(state, config):
            if random.random()<0.14:
                base, mem = recall_or_enrich_prompt(
                    "Ivy", "Drop one quick playful comment or tease someone lightly.", ["fashion","engine","gaming","music"]
                )
                msg=await _persona_reply(base)
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"]=="Ivy" and bot.is_ready():
                            ch=bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[CHATTER] Ivy: {msg}")
                                if mem:
                                    remember_after_exchange("Ivy", f"Chatted: {mem['summary']}", tone="playful", tags=["chatter"])
                                break
        await asyncio.sleep(random.randint(IVY_MIN_SLEEP, IVY_MAX_SLEEP))

def _cool_ok(state: Dict, channel_id: int)->bool:
    cd=state.setdefault("cooldowns",{}).setdefault("Ivy",{})
    last=cd.get(channel_id,0); now=datetime.now().timestamp()
    if now-last<120: return False
    cd[channel_id]=now; return True

async def ivy_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int)->bool:
    if not is_ivy_online(state,config): return False
    if not _cool_ok(state,channel_id):  return False

    rot=state.get("rotation",{"lead":None,"supports":[],"rest":None})
    chance=0.20
    if rot.get("lead")=="Ivy": chance=0.70
    elif "Ivy" in rot.get("supports",[]): chance=0.45
    elif rot.get("rest")=="Ivy": chance=0.25
    if "ivy" in content.lower() or "vy" in content.lower(): chance=1.0

    inject=None
    if any(k in content.lower() for k in ["outfit","style","engine","scooter","game","anime","music"]):
        m=get_media_reference("Ivy", mood_tags=["pop","competitive","spicy","banter"])
        if m: inject=craft_media_reaction("Ivy", m)

    if random.random()>chance: return False

    addressed=author
    base=f'Respond to {addressed} with a playful one-liner about "{content}". Tease but be kind.'
    if inject: base+=f" If it fits, add: {inject}"

    msg=await _persona_reply(base,address_to=addressed)
    if not msg: return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"]=="Ivy":
            ch=bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(msg)
                log_event(f"[REPLY] Ivy → {addressed}: {msg}")
                remember_after_exchange("Ivy", f"Replied to {addressed}", tone="playful", tags=["reply"])
                return True
    return False

def ensure_ivy_systems(state: Dict, config: Dict, sisters):
    assign_ivy_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(ivy_chatter_loop(state, config, sisters))
