import os, json, random, asyncio
from datetime import datetime
from typing import Dict, List

from llm import generate_llm_reply
from logger import log_event

try:
    from image_utils import generate_and_post_outfit
except Exception:
    generate_and_post_outfit = None

PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
MEMORY_JSON      = "/Autonomy/memory/Selene_Memory.json"

MIN_SLEEP = 45 * 60
MAX_SLEEP = 110 * 60
SPONT_OUTFIT_MAX_PER_DAY = 1
SPONT_OUTFIT_PROB = 0.10
SPONT_CHAT_BASE = 0.12
MENTION_FORCE = True

def _load_json(p, d):
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[Selene][WARN] read {p} failed: {e}")
    return d

def _save_json(p, data):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[Selene][WARN] write {p} failed: {e}")

def load_profile() -> Dict:
    d = _load_json(PERSONALITY_JSON, {})
    d.setdefault("core_personality", "Affectionate, nurturing, quietly witty.")
    d.setdefault("likes", ["cozy cooking", "care rituals", "slow mornings"])
    d.setdefault("style", ["soft", "warm", "gentle"])
    return d

def load_memory() -> Dict:
    d = _load_json(MEMORY_JSON, {"projects": {}, "recent_notes": [], "outfits_today": 0, "last_outfit_day": None})
    return d

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
    key, kd = "selene_schedule", "selene_schedule_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Selene", {"wake": [7, 9], "sleep": [22, 23]})
    sch = {"wake": _pick_hour(scfg["wake"]), "sleep": _pick_hour(scfg["sleep"])}
    state[key] = sch; state[kd] = today; return sch

def is_online(state: Dict, config: Dict) -> bool:
    sc = assign_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

async def _persona_reply(base_prompt: str, extra_warm: bool = False) -> str:
    p = load_profile()
    tone = "extra warm, big-sister soothing" if extra_warm else "warm, cozy, lightly teasing"
    prompt = (
        f"You are Selene. Personality: {p.get('core_personality')}. "
        f"Speak in a soft, warm tone, {tone}. "
        f"Keep it brief, present, and affectionate. {base_prompt}"
    )
    return await generate_llm_reply("Selene", prompt, None, "sister", [])

async def maybe_daily_outfit_post(state, config, sisters):
    mem = load_memory(); today_s = str(datetime.now().date())
    if mem.get("last_outfit_day") != today_s: mem["last_outfit_day"]=today_s; mem["outfits_today"]=0
    if mem["outfits_today"] > 0 or not generate_and_post_outfit: return
    try:
        await generate_and_post_outfit("Selene", state, config, sisters, reason="daily_wake")
        mem["outfits_today"] += 1; save_memory(mem)
    except Exception as e: log_event(f"[Selene][WARN] daily outfit failed: {e}")

async def maybe_spont_outfit_change(state, config, sisters):
    mem = load_memory(); today_s = str(datetime.now().date())
    if mem.get("last_outfit_day") != today_s: mem["last_outfit_day"]=today_s; mem["outfits_today"]=0
    if mem["outfits_today"] >= SPONT_OUTFIT_MAX_PER_DAY or not generate_and_post_outfit: return
    if random.random() < SPONT_OUTFIT_PROB:
        try:
            await generate_and_post_outfit("Selene", state, config, sisters, reason="midday_adjust")
            mem["outfits_today"] += 1; save_memory(mem)
        except Exception as e: log_event(f"[Selene][WARN] spont outfit failed: {e}")

async def selene_chatter_loop(state, config, sisters):
    if state.get("selene_chatter_started"): return
    state["selene_chatter_started"] = True
    while True:
        if is_online(state, config):
            await maybe_daily_outfit_post(state, config, sisters)
            if random.random() < SPONT_CHAT_BASE:
                try:
                    msg = await _persona_reply("Say a short, cozy sibling comment; lightly playful; keep it natural.",
                                               extra_warm=(random.random()<0.4))
                    if msg:
                        for bot in sisters:
                            if bot.is_ready() and bot.sister_info["name"] == "Selene":
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch: await ch.send(msg); log_event(f"[Selene][CHAT] {msg}")
                except Exception as e: log_event(f"[Selene][ERR] chatter: {e}")
            await maybe_spont_outfit_change(state, config, sisters)
        await asyncio.sleep(random.randint(MIN_SLEEP, MAX_SLEEP))

async def selene_handle_message(state, config, sisters, author, content, channel_id):
    if not is_online(state, config): return
    chance = 0.20
    if "selene" in content.lower() and MENTION_FORCE: chance = 1.0
    if random.random() >= chance: return
    try:
        reply = await _persona_reply(f'{author} said: "{content}". Reply warmly, big-sister vibe, 1–2 lines.',
                                     extra_warm=(random.random()<0.5))
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Selene":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch: await ch.send(reply); log_event(f"[Selene][REPLY] to {author}: {reply}")
    except Exception as e: log_event(f"[Selene][ERR] reactive: {e}")

def ensure_selene_systems(state, config, sisters):
    assign_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(selene_chatter_loop(state, config, sisters))
