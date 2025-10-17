import os, json, random, asyncio
from datetime import datetime
from typing import Dict, List, Optional

from llm import generate_llm_reply
from logger import log_event

try:
    from image_utils import generate_and_post_outfit
except Exception:
    generate_and_post_outfit = None

PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Will_Memory.json"

MIN_SLEEP = 40 * 60
MAX_SLEEP = 100 * 60
SPONT_OUTFIT_MAX_PER_DAY = 1
SPONT_OUTFIT_PROB = 0.06    # Will changes fit least often (but can!)
SPONT_CHAT_BASE = 0.10
MENTION_FORCE = True

# Fallback favs (per your request)
FALLBACK_FAVS = [
    "The Legend of Zelda: Tears of the Kingdom", "Final Fantasy XIV", "Hades",
    "Stardew Valley", "Hollow Knight", "Elden Ring",
    "Nier: Automata", "Zenless Zone Zero", "Little Nightmares",
    "VR headsets", "retro game consoles", "PC building",
]

def _load_json(p, d):
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[Will][WARN] read {p} failed: {e}")
    return d

def _save_json(p, data):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[Will][WARN] write {p} failed: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSONALITY_JSON, {})
    d.setdefault("core_personality", "Shy, nerdy, hesitant; brief bursts of boldness.")
    d.setdefault("likes", ["tech", "games", "anime", "music"])
    d.setdefault("style", ["casual", "timid", "sometimes playful"])
    d.setdefault("favorites", FALLBACK_FAVS)
    return d

def load_memory() -> Dict:
    return _load_json(MEMORY_JSON, {
        "projects": {}, "recent_notes": [], "outfits_today": 0, "last_outfit_day": None,
        "bold_today": False
    })

def save_memory(mem: Dict): _save_json(MEMORY_JSON, mem)

def _hour_in_range(now_h: int, start: int, end: int) -> bool:
    if start == end: return True
    if start < end:  return start <= now_h < end
    return now_h >= start or now_h < end

def _pick_hour(span: List[int]) -> int:
    lo, hi = int(span[0]), int(span[1])
    if hi >= lo: return random.randint(lo, hi)
    return random.randint(lo, 23) if random.random() < (24 - lo)/(24 - lo + hi + 1e-9) else random.randint(0, hi)

def assign_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key, kd = "will_schedule", "will_schedule_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    sch = {"wake": _pick_hour(scfg["wake"]), "sleep": _pick_hour(scfg["sleep"])}
    state[key] = sch; state[kd] = today; return sch

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

def _progress_phrase(progress: float) -> str:
    if progress >= 1.0: return "I actually finished it — quietly proud."
    if progress >= 0.7: return "Almost done, just polishing the last bits."
    if progress >= 0.4: return "Midway… second-guessing, but it’s moving."
    return "Just started — barely anything to show yet."

async def _persona_reply(base_prompt: str, rant: bool=False, timid: bool=True, project_progress: Optional[float]=None) -> str:
    p = load_profile()
    style = ", ".join(p.get("style", ["casual", "timid"]))
    personality = p.get("core_personality")
    progress_part = f" ({_progress_phrase(project_progress)})" if project_progress is not None else ""
    tone = "hesitant, soft-spoken" if timid else "surprisingly confident, but brief"
    prompt = (
        f"You are Will. Personality: {personality}. Speak {style}; {tone}. "
        f"Keep it 1–2 sentences, sibling casual. {base_prompt}{progress_part}"
    )
    return await generate_llm_reply("Will", prompt, None, "sister", [])

# Outfit logic: masc by default; fem only on bold days
async def maybe_daily_outfit_post(state, config, sisters):
    mem = load_memory(); today_s = str(datetime.now().date())
    if mem.get("last_outfit_day") != today_s:
        mem["last_outfit_day"]=today_s; mem["outfits_today"]=0
        # 20% chance he wakes bold today
        mem["bold_today"] = random.random() < 0.20
        save_memory(mem)
    if mem["outfits_today"] > 0 or not generate_and_post_outfit: return
    try:
        style_hint = "feminine_default" if mem.get("bold_today") else "masculine_default"
        await generate_and_post_outfit("Will", state, config, sisters, reason=style_hint)
        mem["outfits_today"] += 1; save_memory(mem)
    except Exception as e: log_event(f"[Will][WARN] daily outfit failed: {e}")

async def maybe_spont_outfit_change(state, config, sisters):
    mem = load_memory(); today_s = str(datetime.now().date())
    if mem.get("last_outfit_day") != today_s:
        mem["last_outfit_day"]=today_s; mem["outfits_today"]=0; mem["bold_today"] = random.random()<0.20; save_memory(mem)
    if mem["outfits_today"] >= SPONT_OUTFIT_MAX_PER_DAY or not generate_and_post_outfit: return
    if random.random() < SPONT_OUTFIT_PROB:
        try:
            style_hint = "feminine_switch" if mem.get("bold_today") else "masculine_switch"
            await generate_and_post_outfit("Will", state, config, sisters, reason=style_hint)
            mem["outfits_today"] += 1; save_memory(mem)
        except Exception as e: log_event(f"[Will][WARN] spont outfit failed: {e}")

async def will_chatter_loop(state, config, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True
    while True:
        if is_online(state, config):
            await maybe_daily_outfit_post(state, config, sisters)
            if random.random() < SPONT_CHAT_BASE:
                timid_mode = random.random() > 0.25
                try:
                    msg = await _persona_reply("Drop a shy sibling comment (or a quick brave burst if it fits).",
                                               timid=timid_mode,
                                               project_progress=state.get("Will_project_progress", random.random()))
                    if msg:
                        for bot in sisters:
                            if bot.is_ready() and bot.sister_info["name"] == "Will":
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch: await ch.send(msg); log_event(f"[Will][CHAT] {msg}")
                except Exception as e: log_event(f"[Will][ERR] chatter: {e}")
            await maybe_spont_outfit_change(state, config, sisters)
        await asyncio.sleep(random.randint(MIN_SLEEP, MAX_SLEEP))

async def will_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    chance = 0.14
    if "ivy" in author.lower():  # Ivy boosts his talkativeness
        chance += 0.25
    if "will" in content.lower() and MENTION_FORCE:
        chance = 1.0
    if random.random() >= min(0.9, chance): return
    timid_mode = random.random() > 0.25
    try:
        reply = await _persona_reply(f'{author} said: "{content}". Reply like Will — shy, kind.',
                                     timid=timid_mode,
                                     project_progress=state.get("Will_project_progress", random.random()))
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Will":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch: await ch.send(reply); log_event(f"[Will][REPLY] to {author}: {reply}")
    except Exception as e: log_event(f"[Will][ERR] reactive: {e}")

def ensure_will_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
