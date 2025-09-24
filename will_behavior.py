import os
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# ---------------- Defaults ----------------
DEFAULT_PROFILE_PATHS = [
    "data/Will_Profile.txt",
    "/mnt/data/Will_Profile.txt",
]

WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

# Chatter pacing (seconds)
WILL_MIN_SLEEP = 35 * 60
WILL_MAX_SLEEP = 95 * 60

# Probability & behavior
INTEREST_HIT_BOOST = 0.35
DRAMATIC_SHIFT_BASE = 0.05
RANT_CHANCE = 0.10
BANTER_CHANCE = 0.12   # playful sibling banter

# Master favorites pool
WILL_FAVORITES_POOL = [
    "Legend of Zelda", "Final Fantasy", "League of Legends",
    "Attack on Titan", "Demon Slayer", "My Hero Academia",
    "Star Wars", "Marvel movies", "PC building", "retro game consoles",
    "new anime OSTs", "VR headsets", "streaming marathons",
    "indie games", "tech reviews", "cosplay communities",
]

# Expansion pool for periodic growth
FAVORITES_EXPANSION_POOL = [
    "Elden Ring DLC", "Baldur’s Gate 3", "One Piece live-action",
    "Chainsaw Man", "Cyberpunk Edgerunners", "AI companions",
    "mechanical keyboards", "esports tournaments", "3D printing",
]

# ---------------- Helpers ----------------
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
    """Load Will’s personality/interests from TXT, fallback to defaults."""
    text = _read_file_first(DEFAULT_PROFILE_PATHS) or ""
    profile = {
        "interests": ["tech", "games", "anime", "music"],
        "dislikes": ["drama"],
        "style": ["casual", "snarky"],
        "triggers": ["hype", "memes", "nostalgia"],
        "favorites": WILL_FAVORITES_POOL[:],  # copy base pool
    }
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("interests:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["interests"] = vals
        elif low.startswith("dislikes:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["dislikes"] = vals
        elif low.startswith("style:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["style"] = vals
        elif low.startswith("triggers:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["triggers"] = vals
        elif low.startswith("favorites:"):
            vals = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            if vals: profile["favorites"] = vals
    return profile


def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)


# ---------------- Favorites rotation ----------------
def expand_favorites_pool(state: Dict, config: Dict):
    """Once per week, add a new item from expansion pool to favorites."""
    today = datetime.now().date()
    last_expand = state.get("favorites_last_expand")

    if last_expand == today:
        return

    # Expand on Mondays
    if today.weekday() == 0:
        if FAVORITES_EXPANSION_POOL:
            new_item = FAVORITES_EXPANSION_POOL.pop(0)
            pool = state.setdefault("will_favorites_master", WILL_FAVORITES_POOL[:])
            if new_item not in pool:
                pool.append(new_item)
                log_event(f"[WILL] Expanded favorites pool with: {new_item}")
        state["favorites_last_expand"] = today


def get_rotating_favorites(state: Dict, config: Dict, count: int = 3) -> List[str]:
    """Rotate Will's favorites daily so rants feel focused."""
    expand_favorites_pool(state, config)
    today = datetime.now().date()
    key = "will_favorites_today"

    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]

    pool = state.get("will_favorites_master", WILL_FAVORITES_POOL[:])
    picks = random.sample(pool, min(count, len(pool)))

    state[key] = picks
    state[f"{key}_date"] = today
    return picks


# ---------------- Messaging ----------------
async def _post_to_family(message: str, sender: str, sisters, config: Dict):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break


# ---------------- Persona wrapper ----------------
async def _persona_reply(base_prompt: str, rant: bool = False,
                         state: Dict = None, config: Dict = None,
                         address: str = "", escalate: bool = False) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual"]))
    personality = "Casual, nerdy, sometimes dramatic. Younger brother energy."

    tangent = ""
    if rant and state is not None and config is not None:
        favorites_today = get_rotating_favorites(state, config)
        if favorites_today and random.random() < 0.7:
            tangent = f" Mention something about {random.choice(favorites_today)}."

    escalation = " Dial up the sass, extra snarky or mock-dramatic." if escalate else ""

    extra = (
        f"Make it ranty/animated, 2–3 sentences, playful but dramatic.{tangent}{escalation}"
        if rant else
        f"Keep it short (1–2 sentences), {style}, brotherly and casual.{escalation}"
    )

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"Swearing is allowed if natural. "
        f"{base_prompt}{address} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )


# ---------------- Banter / Rant Logic ----------------
def calculate_rant_chance(base: float, interest_score: float = 0, trigger_score: float = 0) -> float:
    now_hour = datetime.now().hour
    rant_chance = base
    if 20 <= now_hour or now_hour <= 1:
        rant_chance *= 2
    if interest_score > 0:
        rant_chance += 0.15
    if trigger_score > 0:
        rant_chance += 0.20
    return min(rant_chance, 1.0)


# ---------------- Chatter Loop ----------------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.18
            if random.random() < 0.08: base_p += 0.10
            try:
                # Banter mode
                if random.random() < BANTER_CHANCE:
                    targets = [s["name"] for s in config["rotation"] if s["name"] != "Will"]
                    if targets:
                        sister = random.choice(targets)
                        last_target = state.get("banter_last_target")
                        escalate = last_target == sister
                        msg = await _persona_reply(
                            f"Start playful banter with {sister}. Tease them lightly but affectionately.",
                            rant=False, state=state, config=config,
                            address=f" Mention {sister} by name.", escalate=escalate
                        )
                        if msg:
                            await _post_to_family(msg, "Will", sisters, config)
                            state["banter_last_target"] = sister

                # Normal chatter
                elif random.random() < base_p:
                    rant_mode = random.random() < calculate_rant_chance(RANT_CHANCE)
                    msg = await _persona_reply("Write a group chat comment.",
                                               rant=rant_mode, state=state, config=config)
                    if msg: await _post_to_family(msg, "Will", sisters, config)

            except Exception as e:
                log_event(f"[ERROR] Will chatter: {e}")

        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))


# ---------------- Reactive Handler ----------------
async def will_handle_message(state: Dict, config: Dict, sisters,
                              author: str, content: str, channel_id: int):
    if not is_will_online(state, config): return

    profile = load_will_profile()
    interest_score = _topic_match_score(content, profile.get("interests", []))
    trigger_score = _topic_match_score(content, profile.get("triggers", []))

    p = 0.15 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.20)
    p = min(p, 0.85)
    if random.random() >= p: return

    rant_chance = calculate_rant_chance(RANT_CHANCE, interest_score, trigger_score)
    rant_mode = random.random() < rant_chance

    address = ""
    if random.random() < 0.4 and author in [s["name"] for s in config["rotation"]]:
        address = f" Mention {author} by name in your reply."

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\". Reply like Will would.",
            rant=rant_mode, state=state, config=config, address=address
        )
        if reply: await _post_to_family(reply, "Will", sisters, config)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")


# ---------------- Schedule ----------------
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "will_schedule"
    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]

    scfg = config.get("schedules", {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    wake_rng = scfg.get("wake", [10, 12])
    sleep_rng = scfg.get("sleep", [0, 2])

    def _pick(hr):
        lo, hi = int(hr[0]), int(hr[1])
        return random.randint(lo, hi) if hi >= lo else lo

    schedule = {"wake": _pick(wake_rng), "sleep": _pick(sleep_rng)}
    state[key] = schedule
    state[f"{key}_date"] = today
    return schedule


def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_hour = datetime.now().hour
    wake, sleep = sc["wake"], sc["sleep"]
    if wake == sleep: return True
    if wake < sleep: return wake <= now_hour < sleep
    return now_hour >= wake or now_hour < sleep


# ---------------- Startup ----------------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
