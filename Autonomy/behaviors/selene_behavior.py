import os, json, random, asyncio
from datetime import datetime
from llm import generate_llm_reply
from logger import log_event

SELENE_PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
SELENE_MEMORY_JSON      = "/Autonomy/memory/Selene_Memory.json"

SELENE_MIN_SLEEP = 45 * 60
SELENE_MAX_SLEEP = 110 * 60

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Selene JSON read failed: {e}")
    return default

def load_selene_profile():
    # Selene = cozy caregiver + surprising love of horror podcasts (contradictory spice)
    return _load_json(SELENE_PERSONALITY_JSON, {
        "interests": ["cozy cooking", "soft music", "homey decor", "horror podcasts"],
        "style": ["soothing", "affectionate", "grounding"]
    })

def load_selene_memory():
    mem = _load_json(SELENE_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_selene_memory(mem):
    try:
        os.makedirs(os.path.dirname(SELENE_MEMORY_JSON), exist_ok=True)
        with open(SELENE_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Selene memory write failed: {e}")

# ------------------ SCHEDULE ------------------

def _pick_range(span):
    lo, hi = int(span[0]), int(span[1])
    if hi < lo: lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_selene_schedule(state, config):
    today = datetime.now().date()
    key, kd = "selene_schedule", "selene_schedule_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Selene", {"wake": [7, 9], "sleep": [22, 23]})
    state[key] = {"wake": _pick_range(scfg["wake"]), "sleep": _pick_range(scfg["sleep"])}
    state[kd] = today
    return state[key]

def _hour_in_range(now, wake, sleep):
    return True if wake == sleep else (wake <= now < sleep if wake < sleep else now >= wake or now < sleep)

def is_selene_online(state, config):
    sc = assign_selene_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# ------------------ CHATTY MODES ------------------

SELENE_MODES = ["cozy", "big-sis", "teasing-soft", "lightly-mischievous"]

async def selene_chatter_loop(state, config, sisters):
    if state.get("selene_chatter_started"): return
    state["selene_chatter_started"] = True
    while True:
        if is_selene_online(state, config) and random.random() < 0.10:
            recent = [m for m in state.get("recent_messages", []) if m["author"] != "Selene"][-4:]
            context = " ".join([f'{m["author"]}: "{m["content"]}"' for m in recent]) or "Quiet room."
            mode = random.choice(SELENE_MODES)
            progress = state.get("Selene_project_progress", random.random())
            prompt = (
                f"Family context: {context}\nSpeak as Selene in a {mode} tone—warm, soothing, playful big-sister energy. "
                f"Keep it short (2–3 sentences). If natural, casually reference a homey project (~{int(progress*100)}%)."
            )
            try:
                msg = await generate_llm_reply("Selene", prompt, theme=None, role="sister", history=[])
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Selene" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[SELENE CHATTER] {msg}")
                                state.setdefault("recent_messages", []).append({"author":"Selene","content":msg})
                                state["recent_messages"] = state["recent_messages"][-25:]
            except Exception as e:
                log_event(f"[ERROR] Selene chatter: {e}")
        await asyncio.sleep(random.randint(SELENE_MIN_SLEEP, SELENE_MAX_SLEEP))

async def selene_handle_message(state, config, sisters, author, content, channel_id):
    if not is_selene_online(state, config): return
    mentioned = "selene" in content.lower()
    p = 0.18 + 0.08 * sum(1 for kw in load_selene_profile().get("interests", []) if kw.lower() in content.lower())
    if mentioned: p = 1.0
    if random.random() >= min(0.95, p): return

    recent = [m for m in state.get("recent_messages", []) if m["author"] != "Selene"][-3:]
    context = " ".join([f'{m["author"]}: "{m["content"]}"' for m in recent])
    tone = random.choice(SELENE_MODES)
    progress = state.get("Selene_project_progress", random.random())
    prompt = (
        f"Family context: {context}\n{author} said: \"{content}\".\n"
        f"As Selene in a {tone} tone—be sweet, gently teasing or reassuring. 1–2 sentences. "
        f"Reference project (~{int(progress*100)}%) only if natural."
    )
    try:
        reply = await generate_llm_reply("Selene", prompt, theme=None, role="sister", history=[])
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Selene":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[SELENE REPLY] → {author}: {reply}")
                        state.setdefault("recent_messages", []).append({"author":"Selene","content":reply})
                        state["recent_messages"] = state["recent_messages"][-25:]
    except Exception as e:
        log_event(f"[ERROR] Selene reactive: {e}")

def ensure_selene_systems(state, config, sisters):
    assign_selene_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(selene_chatter_loop(state, config, sisters))
