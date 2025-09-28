import os
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# Will's dynamic profile loader
DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]

WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60
INTEREST_HIT_BOOST = 0.35
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.10

WILL_FAVORITES_POOL = [
    "Legend of Zelda","Final Fantasy","League of Legends",
    "Attack on Titan","Demon Slayer","My Hero Academia",
    "Star Wars","Marvel movies","PC building",
    "retro game consoles","anime OSTs","VR headsets",
    "streaming marathons","indie games","tech reviews","cosplay communities"
]

def _read_file_first(paths: List[str]) -> Optional[str]:
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
    return None

def load_will_profile() -> Dict:
    text = _read_file_first(DEFAULT_PROFILE_PATHS) or ""
    profile = {
        "interests": ["tech","games","anime","music"],
        "dislikes": ["drama"],
        "style": ["casual","shy","sometimes dramatic"],
        "triggers": ["hype","memes","nostalgia"],
        "favorites": WILL_FAVORITES_POOL,
    }
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("interests:"): profile["interests"] = [x.strip() for x in line.split(":",1)[1].split(",")]
        elif low.startswith("style:"): profile["style"] = [x.strip() for x in line.split(":",1)[1].split(",")]
        elif low.startswith("triggers:"): profile["triggers"] = [x.strip() for x in line.split(":",1)[1].split(",")]
        elif low.startswith("favorites:"): profile["favorites"] = [x.strip() for x in line.split(":",1)[1].split(",")]
    return profile

def get_rotating_favorites(state: Dict, count: int=3) -> List[str]:
    today = datetime.now().date()
    if state.get("will_fav_date") == today and state.get("will_favs"): return state["will_favs"]
    pool = load_will_profile().get("favorites", WILL_FAVORITES_POOL)
    picks = random.sample(pool, min(count, len(pool)))
    state["will_favs"], state["will_fav_date"] = picks, today
    return picks

async def _post_to_family(message: str, sender: str, sisters, config: Dict):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(message)
                log_event(f"{sender}: {message}")
            break

def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    if state.get("will_sched_date") == today and state.get("will_sched"): return state["will_sched"]
    scfg = config.get("schedules", {}).get("Will", {"wake":[10,12],"sleep":[0,2]})
    wake, sleep = random.randint(*scfg["wake"]), random.randint(*scfg["sleep"])
    sched = {"wake": wake,"sleep": sleep}
    state["will_sched"], state["will_sched_date"] = sched, today
    return sched

def is_will_online(state: Dict, config: Dict) -> bool:
    sched = assign_will_schedule(state, config)
    h = datetime.now().hour
    return sched["wake"] <= h < sched["sleep"] if sched["wake"] < sched["sleep"] else h >= sched["wake"] or h < sched["sleep"]

async def _persona_reply(prompt: str, rant: bool=False, state=None) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual"]))
    tangent = ""
    if rant and state:
        favs = get_rotating_favorites(state)
        if favs and random.random()<0.7:
            tangent = f" Mention {random.choice(favs)}."
    extra = "Ranty, 2–3 sentences, playful but shy." if rant else f"Keep it short (1–2 sentences), {style}, shy younger brother."
    full = f"You are Will. Personality: Shy, nerdy, sometimes dramatic. {prompt} {extra}{tangent}"
    return await generate_llm_reply("Will", full, None, "sister", [])

def _topic_match_score(content: str, keys: List[str]) -> float:
    return sum(1 for k in keys if k.lower() in content.lower())

async def will_chatter_loop(state, config, sisters):
    if state.get("will_loop"): return
    state["will_loop"]=True
    while True:
        if is_will_online(state, config) and random.random()<0.2:
            rant = random.random() < 0.1
            msg = await _persona_reply("Say something in group chat.", rant, state)
            if msg: await _post_to_family(msg,"Will",sisters,config)
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

async def will_handle_message(state, config, sisters, author, content, channel_id):
    if not is_will_online(state, config): return
    profile = load_will_profile()
    score = _topic_match_score(content, profile["interests"]+profile["triggers"])
    mention = "will" in content.lower()
    p = 0.15 + score*0.25
    if mention: p = 1.0
    if random.random()<p:
        rant = random.random()<0.1
        reply = await _persona_reply(f"{author} said: \"{content}\". Reply like Will would.", rant, state)
        if reply: await _post_to_family(reply,"Will",sisters,config)

def ensure_will_systems(state, config, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_loop"):
        asyncio.create_task(will_chatter_loop(state,config,sisters))
