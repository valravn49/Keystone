import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# ---------------------------------------------------------------------------
# Profile & memory (lightweight, optional JSONs)
# ---------------------------------------------------------------------------

WILL_PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"
WILL_MEMORY_JSON = "/Autonomy/memory/Will_Memory.json"

WILL_REFINEMENTS_LOG = "data/Will_Refinements_Log.txt"

# Timings (in seconds)
WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

# Probability shaping
INTEREST_HIT_BOOST = 0.35
IVY_BOOST = 0.25
RANT_CHANCE = 0.10

# ---------------------------------------------------------------------------
# Fallback favorites (now includes new titles)
# ---------------------------------------------------------------------------

WILL_FAVORITES_POOL = [
    "The Legend of Zelda: Tears of the Kingdom",
    "Final Fantasy XIV",
    "Hades",
    "Stardew Valley",
    "Hollow Knight",
    "Elden Ring",
    "VR headsets",
    "retro game consoles",
    "PC building",
    "indie game dev videos",
    "tech teardown channels",
    "Nier: Automata",
    "Zenless Zone Zero",
    "Little Nightmares",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Will JSON read failed {path}: {e}")
    return default


def load_will_profile() -> Dict:
    j = _load_json(WILL_PERSONALITY_JSON, {})
    profile = {
        "interests": j.get("interests", ["tech", "games", "anime", "music"]),
        "dislikes": j.get("dislikes", ["drama"]),
        "style": j.get("style", ["casual", "timid", "sometimes playful"]),
        "triggers": j.get("triggers", ["hype", "memes", "nostalgia"]),
        "favorites": j.get("favorites", WILL_FAVORITES_POOL),
    }
    return profile


def load_will_memory() -> Dict:
    mem = _load_json(WILL_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem


def save_will_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(WILL_MEMORY_JSON), exist_ok=True)
        with open(WILL_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Will memory write failed: {e}")

# ---------------------------------------------------------------------------
# Conversation-awareness helpers (shared with sisters)
# ---------------------------------------------------------------------------

def _record_conversation(state: Dict, speaker: str, message: str):
    hist = state.setdefault("conversation_history", [])
    hist.append({"speaker": speaker, "message": message, "timestamp": datetime.now().isoformat()})
    state["conversation_history"] = hist[-15:]


def _get_recent_messages(state: Dict) -> str:
    hist = state.get("conversation_history", [])
    msgs = [f"{h['speaker']}: {h['message']}" for h in hist[-6:]]
    return "\n".join(msgs)


def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords:
        return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)

# ---------------------------------------------------------------------------
# Persona wrapper
# ---------------------------------------------------------------------------

PROGRESS_PHRASES = {
    "early": [
        "I just… started, not much to show yet.",
        "Barely touched it — first step only.",
    ],
    "mid": [
        "It’s coming along slowly — I’ve got a chunk done.",
        "Kinda in the middle, but I keep second-guessing stuff.",
    ],
    "late": [
        "Almost finished — just ironing out the last little bits.",
        "Close to done, I’m just… stalling on the ending.",
    ],
    "done": [
        "I actually finished it — quietly proud, I guess.",
        "Done at last. More relief than excitement.",
    ],
}


def describe_progress(progress: float) -> str:
    if progress >= 1.0:
        return random.choice(PROGRESS_PHRASES["done"])
    elif progress >= 0.7:
        return random.choice(PROGRESS_PHRASES["late"])
    elif progress >= 0.4:
        return random.choice(PROGRESS_PHRASES["mid"])
    else:
        return random.choice(PROGRESS_PHRASES["early"])


async def _persona_reply(
    base_prompt: str,
    rant: bool = False,
    timid: bool = True,
    state: Dict = None,
    config: Dict = None,
    project_progress: Optional[float] = None,
) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual", "timid"]))
    personality = (
        "Shy, nerdy, hesitant; sometimes playful or briefly dramatic when comfortable. "
        "Talks like a younger brother among his sisters — earnest, occasionally flustered."
    )

    history = _get_recent_messages(state)
    tangent = ""
    if rant and state is not None and config is not None:
        favs = profile.get("favorites", WILL_FAVORITES_POOL)
        if favs and random.random() < 0.6:
            tangent = f" Maybe mention {random.choice(favs)}."

    project_phrase = ""
    if project_progress is not None:
        project_phrase = f" Also, about your current project: {describe_progress(project_progress)}"

    tone = "soft-spoken and hesitant" if timid else "a bit more lively and confident"
    extra = (
        f"Make it a small, animated rant (2–3 sentences) but keep the shy undertone.{tangent}{project_phrase}"
        if rant
        else f"Keep it brief (1–2 sentences), {style}, brotherly but {tone}.{project_phrase}"
    )

    prompt = (
        f"You are Will. Personality: {personality} "
        f"Context:\n{history}\n\n"
        f"{base_prompt} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------------------------------------------------------------------------
# Chatter & reaction logic
# ---------------------------------------------------------------------------

async def _post_to_family(message: str, sender: str, sisters, config: Dict):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(message)
                    log_event(f"{sender} posted: {message}")
            except Exception as e:
                log_event(f"[ERROR] Will send: {e}")
            break


async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    """Make Will respond naturally to sisters' messages."""
    profile = load_will_profile()
    interest_score = _topic_match_score(content, profile.get("interests", []))
    trigger_score = _topic_match_score(content, profile.get("triggers", []))

    p = 0.12 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.20)
    if author == "Ivy":
        p += IVY_BOOST
    if "will" in content.lower():
        p = 1.0
    p = min(p, 0.9)

    if random.random() >= p:
        return

    rant_mode = random.random() < RANT_CHANCE
    timid_mode = random.random() > 0.25
    progress = state.get("Will_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply like Will would — casual, sibling tone.',
            rant=rant_mode,
            timid=timid_mode,
            state=state,
            config=config,
            project_progress=progress,
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config)
            _record_conversation(state, "Will", reply)
            log_event(f"[CHAT] Will → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

# ---------------------------------------------------------------------------
# Background chatter
# ---------------------------------------------------------------------------

async def will_chatter_loop(state: Dict, config: Dict, sisters):
    """Will occasionally joins the chat even unprompted, referencing recent context."""
    if state.get("will_chatter_started"):
        return
    state["will_chatter_started"] = True

    while True:
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))
        if random.random() < 0.25:
            rant_mode = random.random() < RANT_CHANCE
            timid_mode = random.random() > 0.25
            progress = state.get("Will_project_progress", random.random())

            try:
                msg = await _persona_reply(
                    "Add a short comment to the ongoing sibling conversation, referencing something recent if natural.",
                    rant=rant_mode,
                    timid=timid_mode,
                    state=state,
                    config=config,
                    project_progress=progress,
                )
                if msg:
                    await _post_to_family(msg, "Will", sisters, config)
                    _record_conversation(state, "Will", msg)
                    log_event(f"[WILL spontaneous]: {msg}")
            except Exception as e:
                log_event(f"[ERROR] Will chatter: {e}")

# ---------------------------------------------------------------------------
# Startup helper
# ---------------------------------------------------------------------------

def ensure_will_systems(state: Dict, config: Dict, sisters):
    """Starts Will’s chatter loop in background."""
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
