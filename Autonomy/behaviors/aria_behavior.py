import os, json, random, asyncio
from datetime import datetime, time
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

# Outfit generator (optional; fail gracefully if missing)
try:
    from image_utils import generate_and_post_outfit
except Exception:
    generate_and_post_outfit = None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PERSONALITY_JSON = "/Autonomy/personalities/Aria_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Aria_Memory.json"

# ---------------------------------------------------------------------------
# Cadence & tuning
# ---------------------------------------------------------------------------
MIN_SLEEP = 50 * 60
MAX_SLEEP = 120 * 60

SPONT_OUTFIT_MAX_PER_DAY = 1        # limited spontaneity
SPONT_OUTFIT_PROB = 0.08            # low chance per chatter tick
SPONT_CHAT_BASE = 0.10              # base chance per tick to say something
MENTION_FORCE = True                # reply if mentioned by name

# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[Aria][WARN] read {path} failed: {e}")
    return default

def _save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[Aria][WARN] write {path} failed: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSONALITY_JSON, {})
    d.setdefault("core_personality", "Calm, methodical, warm, a little shy.")
    d.setdefault("likes", ["organization", "craft", "electronics", "books"])
    d.setdefault("dislikes", [])
    d.setdefault("style", ["structured", "gentle", "practical"])
    return d

def load_memory() -> Dict:
    d = _load_json(MEMORY_JSON, {"projects": {}, "recent_notes": [], "outfits_today": 0})
    d.setdefault("projects", {})
    d.setdefault("recent_notes", [])
    d.setdefault("outfits_today", 0)
    d.setdefault("last_outfit_day", None)
    return d

def save_memory(mem: Dict):
    _save_json(MEMORY_JSON, mem)

# ---------------------------------------------------------------------------
# Schedule helpers (cross-midnight safe)
# ---------------------------------------------------------------------------
def _hour_in_range(now_h: int, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= now_h < end
    return now_h >= start or now_h < end

def _pick_hour(span: List[int]) -> int:
    lo, hi = int(span[0]), int(span[1])
    if hi >= lo:
        return random.randint(lo, hi)
    # wrap window: pick from [lo..23] ∪ [0..hi]
    if random.random() < ((24 - lo) / (24 - lo + hi + 1e-9)):
        return random.randint(lo, 23)
    return random.randint(0, hi)

def assign_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key, kd = "aria_schedule", "aria_schedule_date"
    if state.get(kd) == today and key in state:
        return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Aria", {"wake": [6, 8], "sleep": [22, 23]})
    schedule = {"wake": _pick_hour(scfg["wake"]), "sleep": _pick_hour(scfg["sleep"])}
    state[key] = schedule
    state[kd] = today
    return schedule

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# ---------------------------------------------------------------------------
# Persona reply
# ---------------------------------------------------------------------------
async def _persona_reply(base_prompt: str, reflective: bool = False) -> str:
    p = load_profile()
    style = ", ".join(p.get("style", ["structured", "gentle"]))
    tone = "quietly thoughtful and deliberate" if reflective else "soft, concise, lightly teasing"
    personality = p.get("core_personality", "Calm, methodical, warm.")
    prompt = (
        f"You are Aria. Personality: {personality}. "
        f"Speak in a {style} tone, {tone}. "
        f"Keep it practical and present-focused. {base_prompt}"
    )
    return await generate_llm_reply(
        sister="Aria", user_message=prompt, theme=None, role="sister", history=[]
    )

# ---------------------------------------------------------------------------
# Outfit posting (wake + limited spontaneity)
# ---------------------------------------------------------------------------
async def maybe_daily_outfit_post(state: Dict, config: Dict, sisters):
    mem = load_memory()
    today_s = str(datetime.now().date())
    if mem.get("last_outfit_day") != today_s:
        mem["last_outfit_day"] = today_s
        mem["outfits_today"] = 0
    if mem["outfits_today"] > 0:
        return
    if not generate_and_post_outfit:
        return
    try:
        await generate_and_post_outfit("Aria", state, config, sisters, reason="daily_wake")
        mem["outfits_today"] += 1
        save_memory(mem)
    except Exception as e:
        log_event(f"[Aria][WARN] daily outfit failed: {e}")

async def maybe_spont_outfit_change(state: Dict, config: Dict, sisters):
    mem = load_memory()
    today_s = str(datetime.now().date())
    if mem.get("last_outfit_day") != today_s:
        mem["last_outfit_day"] = today_s
        mem["outfits_today"] = 0
    if mem["outfits_today"] >= SPONT_OUTFIT_MAX_PER_DAY:
        return
    if not generate_and_post_outfit:
        return
    if random.random() < SPONT_OUTFIT_PROB:
        try:
            await generate_and_post_outfit("Aria", state, config, sisters, reason="midday_adjust")
            mem["outfits_today"] += 1
            save_memory(mem)
        except Exception as e:
            log_event(f"[Aria][WARN] spont outfit failed: {e}")

# ---------------------------------------------------------------------------
# Chatter loop
# ---------------------------------------------------------------------------
async def aria_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("aria_chatter_started"):
        return
    state["aria_chatter_started"] = True

    while True:
        if is_online(state, config):
            await maybe_daily_outfit_post(state, config, sisters)
            if random.random() < SPONT_CHAT_BASE:
                reflective = random.random() < 0.35
                try:
                    msg = await _persona_reply(
                        "Say a short, natural sibling comment — practical, present, maybe gently teasing.",
                        reflective=reflective
                    )
                    if msg:
                        for bot in sisters:
                            if bot.is_ready() and bot.sister_info["name"] == "Aria":
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch:
                                    await ch.send(msg)
                                    log_event(f"[Aria][CHAT] {msg}")
                except Exception as e:
                    log_event(f"[Aria][ERR] chatter: {e}")

            await maybe_spont_outfit_change(state, config, sisters)

        await asyncio.sleep(random.randint(MIN_SLEEP, MAX_SLEEP))

# ---------------------------------------------------------------------------
# Reactive
# ---------------------------------------------------------------------------
async def aria_handle_message(state: Dict, config: Dict, sisters, author: str, content: str, channel_id: int):
    if not is_online(state, config):
        return

    chance = 0.18
    if "aria" in content.lower() and MENTION_FORCE:
        chance = 1.0
    if random.random() >= chance:
        return

    reflective = random.random() < 0.5
    try:
        reply = await _persona_reply(
            f'{author} said: "{content}". Reply like an older sister — practical, soft, a little teasing.',
            reflective=reflective
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Aria":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[Aria][REPLY] to {author}: {reply}")
    except Exception as e:
        log_event(f"[Aria][ERR] reactive: {e}")

# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------
def ensure_aria_systems(state: Dict, config: Dict, sisters):
    assign_schedule(state, config)
    if not state.get("aria_chatter_started"):
        asyncio.create_task(aria_chatter_loop(state, config, sisters))
