import os
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event, append_conversation_log
from image_utils import maybe_generate_image_request

DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]

WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

INTEREST_HIT_BOOST = 0.35
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.10

WILL_FAVORITES_POOL = [
    "Legend of Zelda","Final Fantasy","League of Legends",
    "Attack on Titan","Demon Slayer","My Hero Academia",
    "Star Wars","Marvel movies","PC building","retro consoles",
    "anime OSTs","VR headsets","streaming marathons",
    "indie games","tech reviews","cosplay communities",
]

# ---------------- Profile ----------------
def _read_file_first(path_list: List[str]) -> Optional[str]:
    for p in path_list:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                continue
    return None

def load_will_profile() -> Dict:
    text = _read_file_first(DEFAULT_PROFILE_PATHS) or ""
    profile = {
        "interests": ["tech", "games", "anime", "music"],
        "dislikes": ["drama"],
        "style": ["casual", "snarky"],
        "triggers": ["hype", "memes", "nostalgia"],
        "favorites": WILL_FAVORITES_POOL,
    }
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("interests:"):
            profile["interests"] = [x.strip() for x in line.split(":",1)[1].split(",") if x.strip()]
        elif low.startswith("favorites:"):
            profile["favorites"] = [x.strip() for x in line.split(":",1)[1].split(",") if x.strip()]
    return profile

def get_rotating_favorites(state: Dict, config: Dict, count: int = 3) -> List[str]:
    today = datetime.now().date()
    key = "will_favorites_today"
    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]
    pool = load_will_profile().get("favorites", WILL_FAVORITES_POOL)
    picks = random.sample(pool, min(count, len(pool)))
    state[key] = picks
    state[f"{key}_date"] = today
    return picks

# ---------------- Messaging ----------------
async def _post_to_family(message: str, sisters, config: Dict, image=None):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == "Will":
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    if image:
                        await channel.send(message, file=image)
                    else:
                        await channel.send(message)
                    log_event(f"Will posted: {message}")
                    append_conversation_log("Will", "Will", message)
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break

def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "will_schedule"
    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]
    scfg = config.get("schedules", {}).get("Will", {"wake":[10,12],"sleep":[0,2]})
    schedule = {"wake": random.randint(*scfg["wake"]), "sleep": random.randint(*scfg["sleep"])}
    state[key] = schedule
    state[f"{key}_date"] = today
    return schedule

def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_hour = datetime.now().hour
    w, s = sc["wake"], sc["sleep"]
    if w == s: return True
    if w < s: return w <= now_hour < s
    return now_hour >= w or now_hour < s

# ---------------- Persona wrapper ----------------
async def _persona_reply(base_prompt: str, rant=False, state=None, config=None, history=None):
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual"]))
    personality = "Casual, nerdy, sometimes dramatic. Younger brother energy."
    context = "\n".join(history or [])
    tangent = ""
    if rant and state and config:
        favs = get_rotating_favorites(state, config)
        if favs and random.random()<0.7:
            tangent = f" Mention {random.choice(favs)}."
    extra = "Ranty, 2–3 sentences, playful, dramatic."+tangent if rant else f"1–2 sentences, {style}, casual."
    prompt = f"You are Will. Personality: {personality}. Context:\n{context}\n{base_prompt} {extra}"
    msg = await generate_llm_reply("Will", prompt, None, "sister", history or [])
    image = await maybe_generate_image_request("Will", msg, history) if msg else None
    return msg, image

# ---------------- Chatter ----------------
async def will_chatter_loop(state, config, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"]=True
    while True:
        if is_will_online(state, config):
            if random.random()<0.25:
                rant=random.random()<0.1
                try:
                    msg, image = await _persona_reply("Group chat comment.", rant, state, config,
                                                      state.get("history",{}).get("family",[]))
                    if msg: await _post_to_family(msg, sisters, config, image=image)
                except Exception as e: log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------------- Reactive ----------------
async def will_handle_message(state, config, sisters, author, content, channel_id):
    if not is_will_online(state, config): return
    profile=load_will_profile()
    p=0.15+0.35*sum(kw in content.lower() for kw in profile["interests"])
    if random.random()>=min(p,0.85): return
    rant=random.random()<0.15
    try:
        reply, image = await _persona_reply(f"{author} said: \"{content}\" Reply as Will.",
                                            rant,state,config,state.get("history",{}).get("family",[]))
        if reply: await _post_to_family(reply, sisters, config, image=image)
    except Exception as e: log_event(f"[ERROR] Will reactive:
