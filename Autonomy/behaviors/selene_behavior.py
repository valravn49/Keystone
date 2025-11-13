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

SELENE_PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
SELENE_MEMORY_JSON      = "/Autonomy/memory/Selene_Memory.json"

SELENE_MIN_SLEEP = 45 * 60
SELENE_MAX_SLEEP = 100 * 60

NICKNAMES = {
    "Aria": ["Aria", "Ari"], "Selene": ["Selene", "Luna"], "Cassandra": ["Cassandra","Cass","Cassie"],
    "Ivy": ["Ivy","Vy"], "Will": ["Will","Willow"]
}
def _pick_name(t): 
    ns = NICKNAMES.get(t, [t])
    return random.choice(ns) if random.random() < 0.35 else t

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Selene JSON read failed {path}: {e}")
    return default

def load_selene_profile() -> Dict:
    p = _load_json(SELENE_PERSONALITY_JSON, {})
    p.setdefault("style", ["warm", "sensory", "steady"])
    p.setdefault("core_personality", "Nurturing and serene, with a streak for motion and weather.")
    return p

def assign_selene_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key="selene_schedule"; kd=f"{key}_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Selene", {"wake":[7,9],"sleep":[22,24]})
    def pick(span): 
        lo, hi = int(span[0]), int(span[1])
        if hi < lo: lo, hi = hi, lo
        return random.randint(lo, hi)
    schedule={"wake":pick(scfg["wake"]), "sleep":pick(scfg["sleep"])}
    state[key]=schedule; state[kd]=today; return schedule

def _hour_in_range(h,w,s):
    if w==s: return True
    if w<s:  return w<=h<s
    return h>=w or h<s

def is_selene_online(state, config)->bool:
    sc=assign_selene_schedule(state,config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

async def _persona_reply(base_prompt: str, address_to: Optional[str] = None) -> str:
    p = load_selene_profile()
    style = ", ".join(p.get("style", ["warm", "steady"]))
    personality = p.get("core_personality", "Nurturing and serene.")
    who = _pick_name(address_to) if address_to else None
    prefix = f"Speak directly to {who} by name. " if who else ""
    prompt = (
        f"You are Selene. Personality: {personality}. Speak in a {style} style — gentle, sensory, and present. "
        f"{prefix}Only first-person; never refer to yourself in third person. Keep it natural, warm, and specific. "
        f"{base_prompt}"
    )
    return await generate_llm_reply("Selene", prompt, None, "sister", [])

async def selene_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("selene_chatter_started"): return
    state["selene_chatter_started"]=True
    while True:
        if is_selene_online(state, config):
            if random.random()<0.10:
                base, mem = recall_or_enrich_prompt(
                    "Selene", "Offer one cozy check-in or a small sensory observation.", ["kitchen","rain","ride","comfort"]
                )
                msg = await _persona_reply(base)
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"]=="Selene" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[CHATTER] Selene: {msg}")
                                if mem:
                                    remember_after_exchange("Selene", f"Chatted: {mem['summary']}", tone="warm", tags=["chatter"])
                                break
        await asyncio.sleep(random.randint(SELENE_MIN_SLEEP, SELENE_MAX_SLEEP))

def _cool_ok(state: Dict, channel_id: int)->bool:
    cd = state.setdefault("cooldowns", {}).setdefault("Selene", {})
    last = cd.get(channel_id, 0); now = datetime.now().timestamp()
    if now - last < 120: return False
    cd[channel_id]=now; return True

async def selene_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int)->bool:
    if not is_selene_online(state,config): return False
    if not _cool_ok(state,channel_id):     return False

    rot=state.get("rotation", {"lead":None,"supports":[],"rest":None})
    chance=0.20
    if rot.get("lead")=="Selene": chance=0.70
    elif "Selene" in rot.get("supports",[]): chance=0.45
    elif rot.get("rest")=="Selene": chance=0.25
    if "selene" in content.lower(): chance=1.0

    inject=None
    if any(k in content.lower() for k in ["show","anime","movie","soundtrack","music"]):
        m=get_media_reference("Selene", mood_tags=["cozy","feel-good","rain","tea"])
        if m: inject=craft_media_reaction("Selene", m)

    if random.random()>chance: return False

    addressed=author
    base=f'Respond to {addressed} kindly: "{content}". Keep it short, caring, and concrete.'
    if inject: base+=f" If it fits, add: {inject}"

    msg = await _persona_reply(base, address_to=addressed)
    if not msg: return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"]=="Selene":
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(msg)
                log_event(f"[REPLY] Selene → {addressed}: {msg}")
                remember_after_exchange("Selene", f"Replied to {addressed}", tone="warm", tags=["reply"])
                return True
    return False

def ensure_selene_systems(state: Dict, config: Dict, sisters):
    assign_selene_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(selene_chatter_loop(state, config, sisters))
