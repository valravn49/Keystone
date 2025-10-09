import os
import json
import random
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

try:
    import image_utils  # must expose: generate_from_portrait(base_portrait_path, outfit_prompt, save_path)
except Exception:
    image_utils = None

AEDT = ZoneInfo("Australia/Sydney")

# Paths
PERSONALITY_DIR = "/Autonomy/personalities"
MEMORY_DIR = "/Autonomy/memory"
PORTRAIT_DIR = "/Autonomy/portraits"
OUTFIT_DIR = "/Autonomy/outfits"

WILL_PERSONALITY_JSON = os.path.join(PERSONALITY_DIR, "Will.json")
WILL_MEMORY_JSON = os.path.join(MEMORY_DIR, "Will.json")

# Chatter pacing
WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

# Probabilities
INTEREST_HIT_BOOST = 0.35
IVY_BOOST = 0.25
RANT_CHANCE = 0.10

# Favorites fallback
WILL_FAVORITES_POOL = [
    "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
    "Stardew Valley", "Hollow Knight", "Elden Ring",
    "VR headsets", "retro game consoles", "PC building",
    "indie game dev videos", "tech teardown channels",
]

# ---------- JSON helpers ----------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] JSON read fail {path}: {e}")
    return default

def _write_json(path: str, payload: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] JSON write fail {path}: {e}")

def load_will_profile() -> Dict:
    j = _load_json(WILL_PERSONALITY_JSON, {})
    return {
        "interests": j.get("interests", ["tech", "games", "anime", "music"]),
        "dislikes": j.get("dislikes", ["drama"]),
        "style": j.get("style", ["casual", "timid", "sometimes playful"]),
        "triggers": j.get("triggers", ["hype", "memes", "nostalgia"]),
        "favorites": j.get("favorites", WILL_FAVORITES_POOL),
        "confidence": float(j.get("confidence", 0.45)),
        "introversion": float(j.get("introversion", 0.75)),
    }

def load_will_memory() -> Dict:
    mem = _load_json(WILL_MEMORY_JSON, {"projects": {}, "recent_notes": [], "last_outfit_prompt": None})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    mem.setdefault("last_outfit_prompt", None)
    return mem

def save_will_memory(mem: Dict):
    _write_json(WILL_MEMORY_JSON, mem)

# ---------- Favorites rotation ----------
def get_rotating_favorites(state: Dict, config: Dict, count: int = 3) -> List[str]:
    today = datetime.now(AEDT).date()
    key = "will_favorites_today"
    if state.get(f"{key}_date") == today and state.get(key):
        return state[key]
    pool = load_will_profile().get("favorites", WILL_FAVORITES_POOL)
    picks = random.sample(pool, min(count, len(pool)))
    state[key] = picks
    state[f"{key}_date"] = today
    return picks

# ---------- Discord helpers ----------
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

async def _post_image_file(sender: str, sisters, config, path: str):
    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == sender:
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch and os.path.exists(path):
                    import discord
                    file = discord.File(path, filename=os.path.basename(path))
                    await ch.send(file=file)
            except Exception as e:
                log_event(f"[ERROR] Will image send: {e}")
            break

# ---------- Schedule ----------
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now(AEDT).date()
    key, kd = "will_schedule", "will_schedule_date"
    if state.get(kd) == today and state.get(key):
        return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    def pick(span): lo, hi = int(span[0]), int(span[1]); return random.randint(lo, hi) if hi >= lo else lo
    schedule = {"wake": pick(scfg.get("wake", [10,12])), "sleep": pick(scfg.get("sleep", [0,2]))}
    state[key] = schedule
    state[kd] = today
    return schedule

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep: return True
    if wake < sleep: return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    now_h = datetime.now(AEDT).hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

# ---------- Persona wrapper ----------
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
    if progress >= 1.0: return random.choice(PROGRESS_PHRASES["done"])
    if progress >= 0.7: return random.choice(PROGRESS_PHRASES["late"])
    if progress >= 0.4: return random.choice(PROGRESS_PHRASES["mid"])
    return random.choice(PROGRESS_PHRASES["early"])

async def _persona_reply(base_prompt: str, rant: bool, timid: bool, state: Dict, config: Dict, project_progress: Optional[float]) -> str:
    profile = load_will_profile()
    style = ", ".join(profile.get("style", ["casual","timid"]))
    personality = "Shy, nerdy, hesitant; sometimes playful or briefly dramatic."

    tangent = ""
    if rant:
        favs = get_rotating_favorites(state, config)
        if favs and random.random() < 0.6:
            tangent = f" Maybe mention {random.choice(favs)}."

    project_phrase = f" Also, about your project: {describe_progress(project_progress)}" if project_progress is not None else ""

    tone = "hesitant and soft-spoken" if timid else "more outgoing and animated"
    extra = (
        f"Make it a small, animated rant (2–3 sentences) but keep the shy undertone.{tangent}{project_phrase}"
        if rant else
        f"Keep it brief (1–2 sentences), {style}, brotherly but {tone}.{project_phrase}"
    )

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"Swearing is allowed only if it feels natural and mild. "
        f"{base_prompt} {extra}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------- Outfit generation (masc/fem portraits) ----------
def _season_descriptor() -> str:
    m = datetime.now(AEDT).month
    if m in (12,1,2): return "summer"
    if m in (3,4,5): return "autumn"
    if m in (6,7,8): return "winter"
    return "spring"

def _outfit_path(dt: datetime) -> str:
    day = dt.astimezone(AEDT).date().isoformat()
    outdir = os.path.join(OUTFIT_DIR, "Will")
    os.makedirs(outdir, exist_ok=True)
    return os.path.join(outdir, f"{day}_outfit.png")

async def will_generate_and_post_outfit(state: Dict, sisters, config, bold_override: Optional[bool] = None):
    prof = load_will_profile()
    confidence = prof.get("confidence", 0.45)
    intro = prof.get("introversion", 0.75)

    # timid vs bold of the day (override if passed)
    if bold_override is None:
        bold_today = (random.random() < max(0.15, confidence - intro*0.2))
    else:
        bold_today = bold_override

    # Choose portrait
    base_portrait = os.path.join(PORTRAIT_DIR, "Will_Portrait_Fem.png") if bold_today else os.path.join(PORTRAIT_DIR, "Will_Portrait_Masc.png")
    season = _season_descriptor()
    style_line = "clean hoodie + jeans, simple sneakers" if not bold_today else "soft cardigan + pleated skirt, warm tights"
    outfit_prompt = f"Will’s outfit today ({season}): {style_line}. Full-body outfit, consistent with chosen portrait."
    save_path = _outfit_path(datetime.now(AEDT))

    mem = load_will_memory()
    mem["last_outfit_prompt"] = outfit_prompt
    save_will_memory(mem)

    if image_utils and hasattr(image_utils, "generate_from_portrait") and os.path.exists(base_portrait):
        try:
            out = image_utils.generate_from_portrait(
                base_portrait_path=base_portrait,
                outfit_prompt=outfit_prompt,
                save_path=save_path
            )
            if out:
                await _post_to_family(f"🧵 Will — today’s fit ({'bold' if bold_today else 'timid'}):", "Will", sisters, config)
                await _post_image_file("Will", sisters, config, out)
                log_event(f"[OUTFIT] Will generated: {out}")
                return out
        except Exception as e:
            log_event(f"[ERROR] Will outfit gen: {e}")

    await _post_to_family(f"🧵 Will — today’s fit ({'bold' if bold_today else 'timid'}): {style_line} ({season})", "Will", sisters, config)
    return None

# ---------- Background chatter ----------
def calculate_rant_chance(base: float, interest_score: float = 0, trigger_score: float = 0) -> float:
    now_h = datetime.now(AEDT).hour
    rant = base * (2 if (20 <= now_h or now_h <= 1) else 1)
    if interest_score > 0: rant += 0.15
    if trigger_score > 0: rant += 0.20
    return min(rant, 1.0)

async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            base_p = 0.10
            if random.random() < 0.05: base_p += 0.10
            if random.random() < base_p:
                rant_mode = (random.random() < calculate_rant_chance(RANT_CHANCE))
                timid_mode = (random.random() > 0.25)
                progress = state.get("Will_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Drop a short, natural group-chat comment.",
                        rant=rant_mode, timid=timid_mode,
                        state=state, config=config,
                        project_progress=progress
                    )
                    if msg:
                        await _post_to_family(msg, "Will", sisters, config)
                except Exception as e:
                    log_event(f"[ERROR] Will chatter: {e}")

            # 25% chance Will changes outfit mid-day (like others)
            if random.random() < 0.25:
                await will_generate_and_post_outfit(state, sisters, config, bold_override=None)

        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------- Reactive handler ----------
def _topic_match_score(content: str, keywords: List[str]) -> float:
    if not content or not keywords: return 0.0
    text = content.lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)

async def will_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_will_online(state, config): return
    prof = load_will_profile()
    interest_score = _topic_match_score(content, prof.get("interests", []))
    trigger_score = _topic_match_score(content, prof.get("triggers", []))

    p = 0.12 + (interest_score * INTEREST_HIT_BOOST) + (trigger_score * 0.20)
    if author == "Ivy": p += IVY_BOOST
    if "will" in content.lower(): p = 1.0
    p = min(p, 0.9)
    if random.random() >= p: return

    rant_mode = (random.random() < calculate_rant_chance(RANT_CHANCE, interest_score, trigger_score))
    timid_mode = (random.random() > 0.25)
    progress = state.get("Will_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply like Will would.',
            rant=rant_mode, timid=timid_mode,
            state=state, config=config, project_progress=progress
        )
        if reply:
            await _post_to_family(reply, "Will", sisters, config)
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

# ---------- Startup ----------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
